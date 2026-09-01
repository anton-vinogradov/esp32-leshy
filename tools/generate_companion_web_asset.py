#!/usr/bin/env python3
"""Generate deterministic bounded gzip forms of the local Web UI assets."""

from __future__ import annotations

import argparse
import binascii
import gzip
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
