#!/usr/bin/env python3
"""Deterministic offline companion snapshots and local Target search."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA = "leshy.companion.offline.v1"
KIND = "snapshot"
PROTOCOL = 1
TRANSPORT = "usb_serial_ndjson"
WEB_TRANSPORT = "local_web_json"
TRANSPORTS = {TRANSPORT, WEB_TRANSPORT}
_TOP_LEVEL_KEYS = {
    "schema", "kind", "protocol", "source_transport", "complete",
    "snapshot_id", "counts", "sessions", "targets", "comparison",
}
_SESSION_KEYS = {
    "session_id", "source_id", "generation", "state", "started_us",
    "stopped_us", "observations", "dropped",
}
_TARGET_KEYS = {
    "target_id", "revision", "favorite", "name_hex", "notes_hex",
    "tags_hex", "identities", "evidence",
}
_IDENTITY_KEYS = {"kind", "value", "discriminator"}
_EVIDENCE_KEYS = {"source_id", "generation", "sequence", "observed_us"}
_COMPARISON_KEYS = {"baseline", "current", "counts", "items"}
_COORDINATE_KEYS = {"source_id", "generation"}
_COMPARE_COUNT_KEYS = {"added", "changed", "removed", "unchanged"}
_COMPARE_ITEM_KEYS = {
    "target_id", "class", "changes", "baseline_evidence",
    "current_evidence",
}
_HEX_RE = re.compile(r"^[0-9A-F]*$")


class SnapshotError(ValueError):
    """The offline artifact is malformed, incomplete, or non-canonical."""


def _compact_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def canonical_bytes(snapshot: dict[str, Any]) -> bytes:
    """Return the exact portable representation used for an export file."""
    validate_snapshot(snapshot)
    return _compact_json(snapshot) + b"\n"


def _snapshot_digest(snapshot: dict[str, Any]) -> str:
    payload = dict(snapshot)
    payload.pop("snapshot_id", None)
    return hashlib.sha256(_compact_json(payload)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SnapshotError(message)


def _exact_keys(value: Any, expected: set[str], context: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{context} must be an object")
    actual = set(value)
    _require(actual == expected,
             f"{context} fields mismatch: missing={sorted(expected - actual)} "
             f"unknown={sorted(actual - expected)}")
    return value


def _integer(value: Any, context: str, minimum: int = 0) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool) and
             value >= minimum, f"{context} must be an integer >= {minimum}")
    return value


def _text(value: Any, context: str, maximum: int = 128) -> str:
    _require(isinstance(value, str) and len(value) <= maximum,
             f"{context} must be bounded text")
    return value


def _hex(value: Any, context: str, maximum_bytes: int,
         exact_bytes: int | None = None) -> str:
    text = _text(value, context, maximum_bytes * 2)
    _require(len(text) % 2 == 0 and _HEX_RE.fullmatch(text) is not None,
             f"{context} must be uppercase hexadecimal")
    if exact_bytes is not None:
        _require(len(text) == exact_bytes * 2,
                 f"{context} must contain {exact_bytes} bytes")
    return text


def _utf8_hex(value: Any, context: str, maximum_bytes: int) -> str:
    text = _hex(value, context, maximum_bytes)
    try:
        bytes.fromhex(text).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise SnapshotError(f"{context} is not valid UTF-8") from error
    return text


def _normalize_session(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": value["session_id"],
        "source_id": value["source_id"],
        "generation": value["generation"],
        "state": value["state"],
        "started_us": value["started_us"],
        "stopped_us": value["stopped_us"],
        "observations": value["observations"],
        "dropped": value["dropped"],
    }


def _normalize_target(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_id": value["target_id"],
        "revision": value["revision"],
        "favorite": value["favorite"],
        "name_hex": value["name_hex"],
        "notes_hex": value["notes_hex"],
        "tags_hex": list(value["tags_hex"]),
        "identities": [dict(item) for item in value["identities"]],
        "evidence": [dict(item) for item in value["evidence"]],
    }


def build_snapshot(sessions: list[dict[str, Any]],
                   targets: list[dict[str, Any]],
                   comparison: dict[str, Any],
                   source_transport: str = TRANSPORT) -> dict[str, Any]:
    """Build and validate a complete deterministic snapshot."""
    normalized_sessions = [_normalize_session(item) for item in sessions]
    normalized_targets = [_normalize_target(item) for item in targets]
    normalized_comparison = {
        "baseline": dict(comparison["baseline"]),
        "current": dict(comparison["current"]),
        "counts": dict(comparison["counts"]),
        "items": [dict(item) for item in comparison["items"]],
    }
    snapshot: dict[str, Any] = {
        "schema": SCHEMA,
        "kind": KIND,
        "protocol": PROTOCOL,
        "source_transport": source_transport,
        "complete": True,
        "snapshot_id": "",
        "counts": {
            "sessions": len(normalized_sessions),
            "targets": len(normalized_targets),
            "comparison_items": len(normalized_comparison["items"]),
        },
        "sessions": normalized_sessions,
        "targets": normalized_targets,
        "comparison": normalized_comparison,
    }
    snapshot["snapshot_id"] = _snapshot_digest(snapshot)
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    """Fail closed on shape, bounds, completeness, or digest mismatch."""
    root = _exact_keys(snapshot, _TOP_LEVEL_KEYS, "snapshot")
    _require(root["schema"] == SCHEMA, "unsupported snapshot schema")
    _require(root["kind"] == KIND, "unsupported snapshot kind")
    _require(root["protocol"] == PROTOCOL, "unsupported protocol")
    _require(root["source_transport"] in TRANSPORTS,
             "unsupported source transport")
    _require(root["complete"] is True, "partial snapshot rejected")
    snapshot_id = _text(root["snapshot_id"], "snapshot.snapshot_id", 64)
    _require(re.fullmatch(r"[0-9a-f]{64}", snapshot_id) is not None,
             "snapshot.snapshot_id must be lowercase SHA-256")

    counts = _exact_keys(
        root["counts"], {"sessions", "targets", "comparison_items"},
        "snapshot.counts")
    sessions = root["sessions"]
    targets = root["targets"]
    comparison = _exact_keys(
        root["comparison"], _COMPARISON_KEYS, "snapshot.comparison")
    _require(isinstance(sessions, list) and len(sessions) == 2,
             "snapshot.sessions must contain the comparison pair")
    _require(isinstance(targets, list) and 1 <= len(targets) <= 16,
             "snapshot.targets must be a non-empty bounded list")
    _require(isinstance(comparison["items"], list) and
             len(comparison["items"]) <= 16,
             "snapshot.comparison.items must be a bounded list")
    _require(_integer(counts["sessions"], "counts.sessions") == len(sessions),
             "session count mismatch")
    _require(_integer(counts["targets"], "counts.targets") == len(targets),
             "target count mismatch")
    _require(_integer(counts["comparison_items"],
                      "counts.comparison_items") == len(comparison["items"]),
             "comparison item count mismatch")

    session_coordinates: set[tuple[str, int]] = set()
    for index, item in enumerate(sessions):
        session = _exact_keys(item, _SESSION_KEYS, f"sessions[{index}]")
        _require(bool(_text(session["session_id"],
                            f"sessions[{index}].session_id", 48)),
                 f"sessions[{index}].session_id must not be empty")
        source_id = _hex(session["source_id"],
                         f"sessions[{index}].source_id", 16, 16)
        generation = _integer(
            session["generation"], f"sessions[{index}].generation")
        _require(session["state"] == "stopped",
                 f"sessions[{index}] is not stopped")
        started = _integer(session["started_us"],
                           f"sessions[{index}].started_us")
        stopped = _integer(session["stopped_us"],
                           f"sessions[{index}].stopped_us")
        _require(stopped >= started, f"sessions[{index}] time is inverted")
        _integer(session["observations"],
                 f"sessions[{index}].observations")
        _integer(session["dropped"], f"sessions[{index}].dropped")
        coordinate = (source_id, generation)
        _require(coordinate not in session_coordinates,
                 f"duplicate session coordinate at sessions[{index}]")
        session_coordinates.add(coordinate)

    target_ids: set[str] = set()
    for index, item in enumerate(targets):
        target = _exact_keys(item, _TARGET_KEYS, f"targets[{index}]")
        target_id = _hex(target["target_id"],
                         f"targets[{index}].target_id", 16, 16)
        _require(target_id not in target_ids,
                 f"duplicate target_id at targets[{index}]")
        target_ids.add(target_id)
        _integer(target["revision"], f"targets[{index}].revision")
        _require(isinstance(target["favorite"], bool),
                 f"targets[{index}].favorite must be boolean")
        _utf8_hex(target["name_hex"], f"targets[{index}].name_hex", 48)
        _utf8_hex(target["notes_hex"], f"targets[{index}].notes_hex", 160)
        tags = target["tags_hex"]
        identities = target["identities"]
        evidence = target["evidence"]
        _require(isinstance(tags, list) and len(tags) <= 8,
                 f"targets[{index}].tags_hex must be bounded")
        _require(isinstance(identities, list) and len(identities) <= 16,
                 f"targets[{index}].identities must be bounded")
        _require(isinstance(evidence, list) and len(evidence) <= 16,
                 f"targets[{index}].evidence must be bounded")
        for tag_index, tag in enumerate(tags):
            _utf8_hex(tag, f"targets[{index}].tags_hex[{tag_index}]", 24)
        for identity_index, raw_identity in enumerate(identities):
            identity = _exact_keys(
                raw_identity, _IDENTITY_KEYS,
                f"targets[{index}].identities[{identity_index}]")
            _require(identity["kind"] in {
                "wifi_bssid", "wifi_station", "ble_address",
            }, "identity.kind is unsupported")
            _require(bool(_hex(identity["value"], "identity.value", 32)),
                     "identity.value must not be empty")
            _integer(identity["discriminator"], "identity.discriminator")
        for evidence_index, raw_evidence in enumerate(evidence):
            item_context = f"targets[{index}].evidence[{evidence_index}]"
            evidence_item = _exact_keys(
                raw_evidence, _EVIDENCE_KEYS, item_context)
            _hex(evidence_item["source_id"], f"{item_context}.source_id",
                 16, 16)
            _integer(evidence_item["generation"],
                     f"{item_context}.generation")
            _integer(evidence_item["sequence"], f"{item_context}.sequence")
            _integer(evidence_item["observed_us"],
                     f"{item_context}.observed_us")

    for name in ("baseline", "current"):
        coordinate = _exact_keys(
            comparison[name], _COORDINATE_KEYS, f"comparison.{name}")
        pair = (
            _hex(coordinate["source_id"],
                 f"comparison.{name}.source_id", 16, 16),
            _integer(coordinate["generation"],
                     f"comparison.{name}.generation"),
        )
        _require(pair in session_coordinates,
                 f"comparison.{name} does not reference a session")
    compare_counts = _exact_keys(
        comparison["counts"], _COMPARE_COUNT_KEYS, "comparison.counts")
    for key in sorted(_COMPARE_COUNT_KEYS):
        _integer(compare_counts[key], f"comparison.counts.{key}")
    _require(sum(compare_counts.values()) == len(comparison["items"]),
             "comparison class counts do not match items")
    observed_counts = {key: 0 for key in _COMPARE_COUNT_KEYS}
    compared_ids: set[str] = set()
    for index, raw_item in enumerate(comparison["items"]):
        item = _exact_keys(
            raw_item, _COMPARE_ITEM_KEYS, f"comparison.items[{index}]")
        target_id = _hex(item["target_id"],
                         f"comparison.items[{index}].target_id", 16, 16)
        _require(target_id in target_ids,
                 f"comparison.items[{index}] references an unknown target")
        _require(target_id not in compared_ids,
                 f"duplicate compared target at comparison.items[{index}]")
        compared_ids.add(target_id)
        item_class = item["class"]
        _require(item_class in _COMPARE_COUNT_KEYS,
                 f"invalid class at comparison.items[{index}]")
        observed_counts[item_class] += 1
        _integer(item["changes"], f"comparison.items[{index}].changes")
        _integer(item["baseline_evidence"],
                 f"comparison.items[{index}].baseline_evidence")
        _integer(item["current_evidence"],
                 f"comparison.items[{index}].current_evidence")
    _require(observed_counts == compare_counts,
             "comparison counts do not describe comparison items")
    _require(_snapshot_digest(root) == snapshot_id,
             "snapshot digest mismatch")


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.write_bytes(canonical_bytes(snapshot))


def read_snapshot(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SnapshotError("snapshot is not UTF-8 JSON") from error
    _require(isinstance(value, dict), "snapshot root must be an object")
    validate_snapshot(value)
    _require(raw == canonical_bytes(value), "snapshot is not canonical JSON")
    return value


def _decode_utf8(value: str) -> str:
    return bytes.fromhex(value).decode("utf-8", errors="strict")


def _compact_identity(value: str) -> str:
    return "".join(character for character in value.casefold()
                   if character.isalnum())


def search_snapshot(snapshot: dict[str, Any], query: str) -> list[dict[str, Any]]:
    """Search name, notes, tags and radio identities in stable target order."""
    validate_snapshot(snapshot)
    needle = query.strip().casefold()
    _require(bool(needle), "search query must not be empty")
    compact_needle = _compact_identity(needle)
    matches: list[dict[str, Any]] = []
    for target in snapshot["targets"]:
        fields: list[str] = []
        if needle in _decode_utf8(target["name_hex"]).casefold():
            fields.append("name")
        if needle in _decode_utf8(target["notes_hex"]).casefold():
            fields.append("notes")
        if any(needle in _decode_utf8(tag).casefold()
               for tag in target["tags_hex"]):
            fields.append("tags")
        for identity in target["identities"]:
            kind = identity["kind"].casefold()
            value = identity["value"].casefold()
            if (needle in kind or needle in value or
                    (compact_needle and compact_needle in
                     _compact_identity(identity["value"]))):
                fields.append("identities")
                break
        if fields:
            matches.append({
                "target_id": target["target_id"],
                "matched_fields": fields,
            })
    return matches


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("snapshot", type=Path)
    search = subparsers.add_parser("search")
    search.add_argument("snapshot", type=Path)
    search.add_argument("query")
    args = parser.parse_args()
    try:
        snapshot = read_snapshot(args.snapshot)
        if args.command == "verify":
            result = {
                "schema": SCHEMA,
                "status": "pass",
                "snapshot_id": snapshot["snapshot_id"],
                "counts": snapshot["counts"],
            }
        else:
            result = {
                "schema": SCHEMA,
                "kind": "search_results",
                "snapshot_id": snapshot["snapshot_id"],
                "query": args.query,
                "matches": search_snapshot(snapshot, args.query),
            }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, SnapshotError) as error:
        print(f"FAIL: {error}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
