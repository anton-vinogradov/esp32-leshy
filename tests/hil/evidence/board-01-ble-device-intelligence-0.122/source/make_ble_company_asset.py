#!/usr/bin/env python3
"""Build a pinned fixed-record Bluetooth SIG company-ID asset."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path


DEFAULT_SOURCE = (
    "https://bitbucket.org/bluetooth-SIG/public/raw/main/assigned_numbers/"
    "company_identifiers/company_identifiers.yaml")
NAME_BYTES = 30
RECORD_BYTES = 32
VALUE = re.compile(r"^\s*-\s+value:\s+0x([0-9A-Fa-f]{1,4})\s*$")
NAME = re.compile(r"^\s+name:\s*(.+?)\s*$")


def clean_name(value: str) -> str:
    value = " ".join(value.split())
    for suffix in (
            ", Inc.", ", Inc", " Inc.", " Inc", ", Ltd.", ", Ltd",
            " Ltd.", " Ltd", " Corporation", " Corp.", " Corp", " GmbH",
            " LLC", " Limited", " Co., Ltd.", " Co., Ltd", " Co.,Ltd.",
            " Co.,Ltd", " Co."):
        if (value.lower().endswith(suffix.lower()) and
                len(value) - len(suffix) >= 3):
            value = value[:-len(suffix)].rstrip(" ,.")
            break
    return value.rstrip(" ,.")


def parse_scalar(value: str) -> str:
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value.startswith('"') and value.endswith('"'):
        return json.loads(value)
    return value


def source_bytes(source: str) -> bytes:
    path = Path(source)
    if path.is_file():
        return path.read_bytes()
    request = urllib.request.Request(
        source,
        headers={"User-Agent": "ESP32-Leshy-BLE-Company-Asset/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--source-label")
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parents[1] /
        "firmware/leshy1/assets/bluetooth_companies.bin")
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()

    raw = source_bytes(args.source)
    rows: dict[int, str] = {}
    pending: int | None = None
    for line in raw.decode("utf-8", errors="strict").splitlines():
        value = VALUE.match(line)
        if value:
            pending = int(value.group(1), 16)
            continue
        name = NAME.match(line)
        if name and pending is not None:
            cleaned = clean_name(parse_scalar(name.group(1)))
            if cleaned:
                rows[pending] = cleaned
            pending = None
    if len(rows) < 4_000:
        raise SystemExit(
            f"refusing suspicious Bluetooth SIG source with {len(rows)} rows")

    asset = bytearray()
    for company, name in sorted(rows.items()):
        encoded = name.encode("ascii", errors="ignore")[:NAME_BYTES]
        asset.extend(company.to_bytes(2, "little"))
        asset.extend(encoded)
        asset.extend(b"\0" * (NAME_BYTES - len(encoded)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(asset)
    metadata = {
        "schema": "leshy.ble_company_asset.v1",
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
