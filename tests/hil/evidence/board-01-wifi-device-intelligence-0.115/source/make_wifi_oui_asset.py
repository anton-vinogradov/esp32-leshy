#!/usr/bin/env python3
"""Build the release-pinned, fixed-record Wi-Fi OUI asset from IEEE MA-L CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.request
from pathlib import Path


DEFAULT_SOURCE = "https://standards-oui.ieee.org/oui/oui.csv"
NAME_BYTES = 29
RECORD_BYTES = 32

LEGAL_SUFFIXES = (
    ", inc.", ", inc", " inc.", " inc", ", ltd.", ", ltd", " ltd.",
    " ltd", " co.,ltd.", " co.,ltd", " co., ltd.", " co., ltd", " co.",
    " corporation", " corp.", " technologies", " technology", " gmbh",
    " llc", " limited", " a/s", " b.v.", " s.a.",
)


def clean_name(value: str) -> str:
    value = " ".join(value.split())
    while True:
        lowered = value.lower()
        match = next((suffix for suffix in LEGAL_SUFFIXES
                      if lowered.endswith(suffix)
                      and len(value) - len(suffix) >= 3), None)
        if match is None:
            return value.rstrip(" ,.")
        value = value[:-len(match)].rstrip(" ,.")


def source_bytes(source: str) -> bytes:
    path = Path(source)
    if path.is_file():
        return path.read_bytes()
    if source != DEFAULT_SOURCE and "://" not in source:
        raise SystemExit(f"source file not found: {source}")
    request = urllib.request.Request(
        source,
        headers={
            "User-Agent": "ESP32-Leshy-OUI-Asset/1.0",
            "Accept": "text/csv,*/*;q=0.1",
        })
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--source-label")
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[1] /
        "firmware/leshy1/assets/oui.bin")
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()

    raw = source_bytes(args.source)
    rows: dict[bytes, str] = {}
    text = raw.decode("utf-8-sig", errors="strict")
    for row in csv.DictReader(io.StringIO(text)):
        assignment = (row.get("Assignment") or "").strip().replace("-", "")
        name = clean_name((row.get("Organization Name") or "").strip())
        if len(assignment) != 6 or not name:
            continue
        try:
            prefix = bytes.fromhex(assignment)
        except ValueError:
            continue
        rows[prefix] = name

    if len(rows) < 10_000:
        raise SystemExit(f"refusing suspicious IEEE source with {len(rows)} rows")
    asset = bytearray()
    for prefix, name in sorted(rows.items()):
        encoded = name.encode("ascii", errors="ignore")[:NAME_BYTES]
        asset.extend(prefix)
        asset.extend(encoded)
        asset.extend(b"\0" * (NAME_BYTES - len(encoded)))
    if len(asset) != len(rows) * RECORD_BYTES:
        raise AssertionError("fixed-record OUI asset size mismatch")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(asset)
    metadata = {
        "schema": "leshy.wifi_oui_asset.v1",
        "source": args.source_label or args.source,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "asset_sha256": hashlib.sha256(asset).hexdigest(),
        "records": len(rows),
        "record_bytes": RECORD_BYTES,
        "asset_bytes": len(asset),
    }
    metadata_path = args.metadata or args.output.with_suffix(".json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
