#!/usr/bin/env python3
"""Generate deterministic bounded gzip forms of the local Web UI assets."""

from __future__ import annotations

import argparse
import binascii
import gzip
import json
import re
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "firmware/leshy1/src/services/companion/CompanionWebAdapter.cpp"
DIRECTORY = ROOT / "firmware/leshy1/src/services/companion"
ASSETS = (
    ("index", 'R"LESHYHTML(', ')LESHYHTML"',
     DIRECTORY / "CompanionWebIndexGzip.inc", "kIndexHtmlGzip"),
    ("app", 'R"LESHYJS(', ')LESHYJS"',
     DIRECTORY / "CompanionWebAppGzip.inc", "kAppJavascriptGzip"),
)


def asset_bytes(open_marker: str, close_marker: str) -> bytes:
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index(open_marker) + len(open_marker)
    end = source.index(close_marker, start)
    return source[start:end].encode("utf-8")


def deterministic_gzip(payload: bytes) -> bytes:
    compressor = zlib.compressobj(
        level=9, method=zlib.DEFLATED, wbits=-zlib.MAX_WBITS)
    body = compressor.compress(payload) + compressor.flush()
    header = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"
    trailer = struct.pack(
        "<II", binascii.crc32(payload) & 0xFFFFFFFF,
        len(payload) & 0xFFFFFFFF)
    encoded = header + body + trailer
    if gzip.decompress(encoded) != payload:
        raise RuntimeError("generated gzip does not reproduce the index")
    return encoded


def validate_index_copy(payload: bytes) -> None:
    page = payload.decode("utf-8")
    matches = re.findall(
        r'<script id="copy" type="application/json">(.*?)</script>',
        page, re.DOTALL)
    if len(matches) != 1:
        raise RuntimeError("companion Web index must contain one copy catalog")
    catalog = json.loads(matches[0])
    if set(catalog) != {"en", "ru"}:
        raise RuntimeError("companion Web copy catalog must contain EN and RU")
    if not all(isinstance(catalog[language], dict) for language in catalog):
        raise RuntimeError("companion Web language catalog is not an object")
    if set(catalog["en"]) != set(catalog["ru"]):
        raise RuntimeError("companion Web EN/RU copy keys differ")
    if any(not isinstance(value, str) or not value
           for language in catalog.values() for value in language.values()):
        raise RuntimeError("companion Web copy contains an empty/non-text value")
    static_keys = set(re.findall(r'data-copy="([a-z_]+)"', page))
    missing = static_keys - set(catalog["en"])
    if missing:
        raise RuntimeError(
            f"companion Web static copy keys are missing: {sorted(missing)}")
    required = {
        "brand", "sessions", "targets", "compare", "search", "export",
        "opening", "connecting", "ready", "collecting", "details",
        "favorite", "unfavorite", "no_targets", "no_sessions", "summary",
        "technical_evidence", "confirm_add", "confirm_remove", "building",
        "saved", "unavailable", "error_comparison_requires_two_sessions",
        "error_target_not_found", "error_mutation_timeout",
    }
    missing = required - set(catalog["en"])
    if missing:
        raise RuntimeError(
            f"companion Web task copy is missing: {sorted(missing)}")
    if catalog["en"]["sessions"] == catalog["ru"]["sessions"]:
        raise RuntimeError("companion Web Russian copy was not localized")


def render(encoded: bytes, symbol: str) -> str:
    lines = [f"constexpr std::uint8_t {symbol}[] = {{"]
    for offset in range(0, len(encoded), 12):
        values = ", ".join(
            f"0x{value:02x}" for value in encoded[offset:offset + 12])
        lines.append(f"    {values},")
    lines.append("};")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    results: list[str] = []
    for name, open_marker, close_marker, output, symbol in ASSETS:
        payload = asset_bytes(open_marker, close_marker)
        if name == "index":
            validate_index_copy(payload)
        encoded = deterministic_gzip(payload)
        if len(encoded) >= 4096:
            raise RuntimeError(
                f"compressed {name} exceeds bounded window: {len(encoded)}")
        expected = render(encoded, symbol)
        if args.check:
            if (not output.is_file() or
                    output.read_text(encoding="utf-8") != expected):
                raise RuntimeError(
                    "companion Web gzip asset is stale; run "
                    "tools/generate_companion_web_asset.py")
        else:
            output.write_text(expected, encoding="utf-8")
        results.append(f"{name} {len(payload)} -> {len(encoded)} bytes")
    print("companion Web assets passed: " + "; ".join(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
