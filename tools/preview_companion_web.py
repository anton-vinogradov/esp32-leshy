#!/usr/bin/env python3
"""Serve the embedded companion UI with deterministic local-only demo data."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "firmware/leshy1/src/services/companion/CompanionWebAdapter.cpp"
API_PATH = "/api/v1/companion"


def embedded_asset(open_marker: str, close_marker: str) -> bytes:
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index(open_marker) + len(open_marker)
    end = source.index(close_marker, start)
    return source[start:end].encode("utf-8")


INDEX = embedded_asset('R"LESHYHTML(', ')LESHYHTML"')
APP = embedded_asset('R"LESHYJS(', ')LESHYJS"')


def encoded(text: str) -> str:
    return text.encode("utf-8").hex().upper()


SESSIONS = (
    {
        "session_id": "Дом · утром",
        "source_id": "01000000000000000000000000000000",
        "generation": 40,
        "observations": 83,
        "state": "stopped",
        "started_us": 1_000_000,
        "stopped_us": 4_000_000,
        "dropped": 0,
    },
    {
        "session_id": "Дом · вечером",
        "source_id": "02000000000000000000000000000000",
        "generation": 41,
        "observations": 91,
        "state": "stopped",
        "started_us": 5_000_000,
        "stopped_us": 8_000_000,
        "dropped": 0,
    },
)

TARGETS: dict[str, dict[str, Any]] = {
    "10000000000000000000000000000001": {
        "revision": 7,
        "favorite": True,
        "name_hex": encoded("Рабочий ноутбук"),
        "notes_hex": encoded("Обычно рядом с кабинетом"),
        "tags_hex": [encoded("своё"), encoded("работа")],
        "identities": [
            {"kind": "wifi_bssid", "value": "02:00:00:00:00:01"},
            {"kind": "ble_address", "value": "02:00:00:00:10:01"},
        ],
        "evidence": [
            {"generation": 40, "sequence": 12, "observed_us": 2_100_000},
            {"generation": 41, "sequence": 15, "observed_us": 6_100_000},
        ],
    },
    "10000000000000000000000000000002": {
        "revision": 3,
        "favorite": False,
        "name_hex": encoded("Датчик в гостиной"),
        "notes_hex": encoded("BLE-маяк у окна"),
        "tags_hex": [encoded("дом")],
        "identities": [
            {"kind": "ble_address", "value": "02:00:00:00:10:02"},
        ],
        "evidence": [
            {"generation": 41, "sequence": 22, "observed_us": 6_800_000},
        ],
    },
}


def response(message: dict[str, Any]) -> dict[str, Any]:
    kind = message.get("kind")
    request_id = message.get("request_id", "")
    base = {
        "schema": "leshy.companion.response.v1",
        "kind": kind,
        "request_id": request_id,
        "status": "ok",
    }
    if kind == "connect":
        return {**base, "protocol": 1}
    if kind == "session.list":
        return {**base, "offset": 0, "next_offset": None,
                "items": list(SESSIONS)}
    if kind == "session.detail":
        item = next((item for item in SESSIONS
                     if item["source_id"] == message.get("source_id") and
                     item["generation"] == message.get("generation")), None)
        return {**base, **(item or {})}
    if kind == "target.list":
        items = []
        for target_id, target in TARGETS.items():
            items.append({
                "target_id": target_id,
                "revision": target["revision"],
                "favorite": target["favorite"],
                "name_hex": target["name_hex"],
                "identity_count": len(target["identities"]),
                "evidence_count": len(target["evidence"]),
            })
        return {**base, "offset": 0, "next_offset": None, "items": items}
    if kind == "target.detail":
        target_id = message.get("target_id")
        target = TARGETS.get(target_id)
        if target is None:
            return {**base, "status": "error", "reason": "not_found"}
        section = message.get("section")
        if section == "summary":
            return {**base, "target_id": target_id,
                    "revision": target["revision"],
                    "favorite": target["favorite"],
                    "name_hex": target["name_hex"]}
        if section == "notes":
            return {**base, "value": target["notes_hex"],
                    "next_offset": None}
        values = target["tags_hex"] if section == "tags" else target.get(section)
        if values is None:
            return {**base, "status": "error", "reason": "not_found"}
        return {**base, "offset": 0, "next_offset": None,
                "items": values}
    if kind == "target.compare":
        items = [
            {"target_id": next(iter(TARGETS)), "class": "changed",
             "changes": 2, "baseline_evidence": 1, "current_evidence": 1},
            {"target_id": list(TARGETS)[1], "class": "added",
             "changes": 1, "baseline_evidence": 0, "current_evidence": 1},
        ]
        return {**base, "offset": 0, "next_offset": None,
                "counts": {"added": 1, "removed": 0, "changed": 1,
                           "unchanged": 0}, "items": items}
    if kind == "target.mutation.preview":
        target = TARGETS.get(message.get("target_id"))
        if target is None:
            return {**base, "status": "error", "reason": "not_found"}
        return {**base, "mutation_id": "preview-1",
                "target_revision": target["revision"] + 1}
    if kind == "target.mutation.confirm":
        return {**base, "state": "saving"}
    if kind == "target.mutation.status":
        return {**base, "state": "saved"}
    return {**base, "status": "error", "reason": "unsupported_kind"}


class PreviewHandler(BaseHTTPRequestHandler):
    server_version = "LeshyCompanionPreview/1"

    def send_bytes(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self.send_bytes(200, "text/html; charset=utf-8", INDEX)
        elif self.path == "/app.js":
            self.send_bytes(200, "text/javascript; charset=utf-8", APP)
        else:
            self.send_bytes(404, "text/plain; charset=utf-8", b"not found\n")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != API_PATH:
            self.send_bytes(404, "application/json", b"{}\n")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 512:
                raise ValueError("invalid length")
            message = json.loads(self.rfile.read(length))
            payload = (json.dumps(response(message), ensure_ascii=False,
                                  separators=(",", ":")) + "\n").encode("utf-8")
            self.send_bytes(200, "application/json; charset=utf-8", payload)
        except (ValueError, json.JSONDecodeError):
            self.send_bytes(400, "application/json", b"{}\n")

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), PreviewHandler)
    print(f"companion Web preview: http://127.0.0.1:{server.server_port}/",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
