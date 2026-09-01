#!/usr/bin/env python3
"""Read-only companion HTTP verifier for an already-connected client."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import companion_offline


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "firmware/leshy1/src/services/companion/CompanionWebAdapter.cpp"
REQUEST_SCHEMA = "leshy.companion.request.v1"
RESPONSE_SCHEMA = "leshy.companion.response.v1"
SCOPES = ["session.read", "target.read", "target.compare"]
CAPABILITIES = [
    "session.list", "session.detail", "target.list", "target.detail",
    "target.compare",
]
FIXED_ORIGIN = "http://192.168.4.1"
MAX_ASSET_BYTES = 16_384
MAX_RESPONSE_BYTES = 8_192

Get = Callable[[str], tuple[int, str, bytes]]
Post = Callable[[str, dict[str, Any]], tuple[int, str, dict[str, Any]]]


def embedded_asset(open_marker: str, close_marker: str) -> bytes:
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index(open_marker) + len(open_marker)
    end = source.index(close_marker, start)
    return source[start:end].encode("utf-8")


INDEX = embedded_asset('R"LESHYHTML(', ')LESHYHTML"')
APP = embedded_asset('R"LESHYJS(', ')LESHYJS"')


def validate_origin(value: str) -> str:
    parsed = urlparse(value)
    if (parsed.scheme != "http" or parsed.hostname != "192.168.4.1" or
            parsed.port not in (None, 80) or parsed.username is not None or
            parsed.password is not None or parsed.path not in ("", "/") or
            parsed.params or parsed.query or parsed.fragment):
        raise ValueError(
            "origin must be the fixed direct SoftAP URL http://192.168.4.1")
    return FIXED_ORIGIN


def _opener() -> urllib.request.OpenerDirector:
    # Never let ambient proxy variables redirect the private peer request.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def direct_get(url: str, timeout: float = 15.0) -> tuple[int, str, bytes]:
    request = urllib.request.Request(url, method="GET")
    with _opener().open(request, timeout=timeout) as response:
        length = int(response.headers.get("Content-Length", "-1"))
        if length < 0 or length > MAX_ASSET_BYTES:
            raise RuntimeError("asset Content-Length is missing or unbounded")
        encoded = response.read(length + 1)
        if len(encoded) != length:
            raise RuntimeError("asset body length differs from Content-Length")
        content_encoding = response.headers.get("Content-Encoding", "")
        if content_encoding not in ("", "gzip"):
            raise RuntimeError("asset has an unsupported content encoding")
        decoded = gzip.decompress(encoded) if content_encoding == "gzip" \
            else encoded
        if len(decoded) > MAX_ASSET_BYTES:
            raise RuntimeError("decoded asset exceeds the client bound")
        return response.status, response.headers.get_content_type(), decoded


def direct_post(url: str, payload: dict[str, Any], timeout: float = 10.0) \
        -> tuple[int, str, dict[str, Any]]:
    encoded = json.dumps(payload, separators=(",", ":")).encode("ascii")
    if len(encoded) > 512:
        raise RuntimeError("companion request exceeds 512 bytes")
    request = urllib.request.Request(
        url, data=encoded, method="POST",
        headers={"Content-Type": "application/json"})
    with _opener().open(request, timeout=timeout) as response:
        length = int(response.headers.get("Content-Length", "-1"))
        if length < 0 or length > MAX_RESPONSE_BYTES:
            raise RuntimeError("API Content-Length is missing or unbounded")
        raw = response.read(length + 1)
        if len(raw) != length:
            raise RuntimeError("API body length differs from Content-Length")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise RuntimeError("API response is not an object")
        return response.status, response.headers.get_content_type(), value


class CompanionClient:
    def __init__(self, origin: str, post: Post) -> None:
        self.origin = validate_origin(origin)
        self.api = self.origin + "/api/v1/companion"
        self.post = post
        self.sequence = 0
        self.requests = 0

    def exchange(self, kind: str, **fields: Any) -> dict[str, Any]:
        self.sequence += 1
        request_id = f"external-{self.sequence}"
        request = {
            "schema": REQUEST_SCHEMA,
            "kind": kind,
            "request_id": request_id,
            **fields,
        }
        status, content_type, response = self.post(self.api, request)
        self.requests += 1
        if status != 200 or content_type != "application/json":
            raise RuntimeError("companion endpoint did not return exact JSON")
        if (response.get("schema") != RESPONSE_SCHEMA or
                response.get("kind") != kind or
                response.get("request_id") != request_id):
            raise RuntimeError("companion response identity mismatch")
        if response.get("status") not in ("ok", "ready") or \
                response.get("reason") != "none":
            raise RuntimeError(f"companion request failed: {kind}")
        return response

    def pages(self, kind: str, **fixed: Any) \
            -> tuple[list[Any], list[dict[str, Any]]]:
        offset = 0
        items: list[Any] = []
        pages: list[dict[str, Any]] = []
        for _ in range(64):
            response = self.exchange(kind, offset=offset, **fixed)
            page_items = response.get("items", [])
            if not isinstance(page_items, list):
                raise RuntimeError(f"{kind} items are not a list")
            items.extend(page_items)
            pages.append(response)
            next_offset = response.get("next_offset")
            if next_offset is None:
                return items, pages
            if (not isinstance(next_offset, int) or
                    isinstance(next_offset, bool) or next_offset <= offset):
                raise RuntimeError(f"{kind} pagination did not advance")
            offset = next_offset
        raise RuntimeError(f"{kind} exceeded bounded pagination")

    def notes(self, target_id: str) -> str:
        offset = 0
        value = ""
        for _ in range(4):
            response = self.exchange(
                "target.detail", target_id=target_id, section="notes",
                offset=offset)
            part = response.get("value", "")
            if not isinstance(part, str):
                raise RuntimeError("target notes are not text")
            value += part
            next_offset = response.get("next_offset")
            if next_offset is None:
                return value
            if (not isinstance(next_offset, int) or
                    isinstance(next_offset, bool) or next_offset <= offset):
                raise RuntimeError("target notes pagination did not advance")
            offset = next_offset
        raise RuntimeError("target notes exceeded bounded pagination")

    def target(self, listed: dict[str, Any]) -> dict[str, Any]:
        target_id = listed.get("target_id")
        if not isinstance(target_id, str):
            raise RuntimeError("target list omitted target_id")
        summary = self.exchange(
            "target.detail", target_id=target_id, section="summary", offset=0)
        tags, _ = self.pages(
            "target.detail", target_id=target_id, section="tags")
        identities, _ = self.pages(
            "target.detail", target_id=target_id, section="identities")
        evidence, _ = self.pages(
            "target.detail", target_id=target_id, section="evidence")
        return {
            "target_id": target_id,
            "revision": summary.get("revision"),
            "favorite": summary.get("favorite"),
            "name_hex": summary.get("name_hex"),
            "notes_hex": self.notes(target_id),
            "tags_hex": tags,
            "identities": identities,
            "evidence": evidence,
        }


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _projection_sha256(snapshot: dict[str, Any]) -> str:
    projection = dict(snapshot)
    projection.pop("snapshot_id")
    projection.pop("source_transport")
    encoded = json.dumps(
        projection, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")
    return _sha256(encoded)


def run_probe(origin: str, challenge: str, get: Get = direct_get,
              post: Post = direct_post) -> dict[str, Any]:
    validate_origin(origin)
    if re.fullmatch(r"[0-9a-f]{32}", challenge) is None:
        raise ValueError("challenge must be 16 bytes of lowercase hexadecimal")
    index_status, index_type, index = get(FIXED_ORIGIN + "/")
    app_status, app_type, app = get(FIXED_ORIGIN + "/app.js")
    if (index_status != 200 or index_type != "text/html" or index != INDEX):
        raise RuntimeError("served index differs from the exact production asset")
    if (app_status != 200 or app_type != "text/javascript" or app != APP):
        raise RuntimeError("served application differs from the exact production asset")

    client = CompanionClient(origin, post)
    connected = client.exchange("connect", protocol=1, scopes=SCOPES)
    if (connected.get("transport") != companion_offline.WEB_TRANSPORT or
            connected.get("scopes") != SCOPES or
            connected.get("capabilities") != CAPABILITIES):
        raise RuntimeError("companion connect grant differs from read-only Web")

    listed_sessions, session_pages = client.pages("session.list")
    if len(listed_sessions) != 2:
        raise RuntimeError("exactly two stopped sessions are required")
    sessions = [client.exchange(
        "session.detail", source_id=item.get("source_id"),
        generation=item.get("generation")) for item in listed_sessions]
    listed_targets, target_pages = client.pages("target.list")
    targets = [client.target(item) for item in listed_targets]
    baseline, current = sessions
    compare_fields = {
        "baseline_source_id": baseline.get("source_id"),
        "baseline_generation": baseline.get("generation"),
        "current_source_id": current.get("source_id"),
        "current_generation": current.get("generation"),
    }
    compared, compare_pages = client.pages("target.compare", **compare_fields)
    counts = compare_pages[-1].get("counts") if compare_pages else None
    comparison = {
        "baseline": {
            "source_id": baseline.get("source_id"),
            "generation": baseline.get("generation"),
        },
        "current": {
            "source_id": current.get("source_id"),
            "generation": current.get("generation"),
        },
        "counts": counts,
        "items": compared,
    }
    snapshot = companion_offline.build_snapshot(
        sessions, targets, comparison, companion_offline.WEB_TRANSPORT)
    return {
        "schema": "leshy.companion.external_http_probe.v1",
        "status": "pass",
        "challenge_sha256": _sha256(bytes.fromhex(challenge)),
        "origin": "fixed_private_softap",
        "network_configuration_commands": 0,
        "credential_material_handled": False,
        "assets": {
            "index_bytes": len(index),
            "index_sha256": _sha256(index),
            "application_bytes": len(app),
            "application_sha256": _sha256(app),
            "exact_production_match": True,
        },
        "connection": {
            "transport": connected.get("transport"),
            "scopes": connected.get("scopes"),
            "capabilities": connected.get("capabilities"),
        },
        "projection": {
            "sessions": len(sessions),
            "session_pages": len(session_pages),
            "targets": len(targets),
            "target_pages": len(target_pages),
            "comparison_items": len(compared),
            "comparison_pages": len(compare_pages),
            "snapshot_id": snapshot["snapshot_id"],
            "transport_neutral_sha256": _projection_sha256(snapshot),
        },
        "http_requests": client.requests + 2,
        "raw_target_data_retained": False,
    }


def _write_report(path: Path | None, report: dict[str, Any]) -> None:
    encoded = json.dumps(
        report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path is None:
        sys.stdout.write(encoded)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default=FIXED_ORIGIN)
    parser.add_argument("--challenge", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run_probe(args.origin, args.challenge)
    except (OSError, TimeoutError, ValueError, RuntimeError,
            companion_offline.SnapshotError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    try:
        _write_report(args.output, report)
    except OSError as error:
        print(f"FAIL: cannot write report: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
