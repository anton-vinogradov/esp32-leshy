#!/usr/bin/env python3
"""Bind an external HTTP probe to the same canonical USB projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import companion_offline
import companion_web_external_client as external


ROOT_KEYS = {
    "schema", "status", "challenge_sha256", "origin",
    "network_configuration_commands", "credential_material_handled",
    "assets", "connection", "projection", "http_requests",
    "raw_target_data_retained",
}
ASSET_KEYS = {
    "index_bytes", "index_sha256", "application_bytes",
    "application_sha256", "exact_production_match",
}
CONNECTION_KEYS = {"transport", "scopes", "capabilities"}
PROJECTION_KEYS = {
    "sessions", "session_pages", "targets", "target_pages",
    "comparison_items", "comparison_pages", "snapshot_id",
    "transport_neutral_sha256",
}


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _exact(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{name} must be an object")
    _require(set(value) == keys, f"{name} fields differ from the contract")
    return value


def _positive(value: Any, name: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool) and value > 0,
             f"{name} must be a positive integer")
    return value


def verify(report: dict[str, Any], challenge: str,
           usb_snapshot: dict[str, Any]) -> dict[str, Any]:
    root = _exact(report, ROOT_KEYS, "report")
    _require(root["schema"] == "leshy.companion.external_http_probe.v1",
             "unsupported report schema")
    _require(root["status"] == "pass", "external probe did not pass")
    _require(re.fullmatch(r"[0-9a-f]{32}", challenge) is not None,
             "challenge must be 16 bytes of lowercase hexadecimal")
    expected_challenge = hashlib.sha256(bytes.fromhex(challenge)).hexdigest()
    _require(root["challenge_sha256"] == expected_challenge,
             "external report challenge mismatch")
    _require(root["origin"] == "fixed_private_softap",
             "external report did not use the fixed private origin")
    _require(root["network_configuration_commands"] == 0,
             "external verifier changed network configuration")
    _require(root["credential_material_handled"] is False,
             "external verifier handled credential material")
    _require(root["raw_target_data_retained"] is False,
             "external report retained raw Target data")

    assets = _exact(root["assets"], ASSET_KEYS, "report.assets")
    _require(assets["exact_production_match"] is True,
             "external assets were not exact production bytes")
    _require(assets["index_bytes"] == len(external.INDEX) and
             assets["index_sha256"] == hashlib.sha256(external.INDEX).hexdigest(),
             "external index identity mismatch")
    _require(assets["application_bytes"] == len(external.APP) and
             assets["application_sha256"] == hashlib.sha256(external.APP).hexdigest(),
             "external application identity mismatch")

    connection = _exact(
        root["connection"], CONNECTION_KEYS, "report.connection")
    _require(connection == {
        "transport": companion_offline.WEB_TRANSPORT,
        "scopes": external.SCOPES,
        "capabilities": external.CAPABILITIES,
    }, "external connection grant mismatch")

    companion_offline.validate_snapshot(usb_snapshot)
    _require(usb_snapshot["source_transport"] == companion_offline.TRANSPORT,
             "comparison snapshot is not native USB")
    projection = _exact(
        root["projection"], PROJECTION_KEYS, "report.projection")
    counts = usb_snapshot["counts"]
    _require(projection["sessions"] == counts["sessions"] and
             projection["targets"] == counts["targets"] and
             projection["comparison_items"] == counts["comparison_items"],
             "external and USB projection counts differ")
    for key in ("session_pages", "target_pages", "comparison_pages"):
        _positive(projection[key], f"report.projection.{key}")
    _require(re.fullmatch(r"[0-9a-f]{64}", projection["snapshot_id"] or "")
             is not None, "external snapshot identity is malformed")
    expected_projection = external._projection_sha256(usb_snapshot)
    _require(projection["transport_neutral_sha256"] == expected_projection,
             "external and USB canonical projections differ")
    requests = _positive(root["http_requests"], "report.http_requests")
    return {
        "schema": "leshy.companion.external_http_parity.v1",
        "status": "pass",
        "challenge_sha256": expected_challenge,
        "asset_identity": "exact_production",
        "projection_sha256": expected_projection,
        "counts": dict(counts),
        "http_requests": requests,
        "network_configuration_commands": 0,
        "raw_target_data_retained": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--usb-snapshot", required=True, type=Path)
    parser.add_argument("--challenge", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        snapshot = companion_offline.read_snapshot(args.usb_snapshot)
        accepted = verify(report, args.challenge, snapshot)
        encoded = json.dumps(accepted, sort_keys=True, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(encoded)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as output:
                output.write(encoded)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError,
            ValueError, companion_offline.SnapshotError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
