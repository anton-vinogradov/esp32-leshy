#!/usr/bin/env python3
"""Generate the deterministic bounded gzip form of the local Web index."""

from __future__ import annotations

import argparse
import binascii
import gzip
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "firmware/leshy1/src/services/companion/CompanionWebAdapter.cpp"
OUTPUT = ROOT / "firmware/leshy1/src/services/companion/CompanionWebIndexGzip.inc"
OPEN = 'R"LESHYHTML('
CLOSE = ')LESHYHTML"'


def html_bytes() -> bytes:
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index(OPEN) + len(OPEN)
    end = source.index(CLOSE, start)
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


def render(encoded: bytes) -> str:
    lines = ["constexpr std::uint8_t kIndexHtmlGzip[] = {"]
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
    payload = html_bytes()
    encoded = deterministic_gzip(payload)
    if len(encoded) >= 4096:
        raise RuntimeError(
            f"compressed index exceeds bounded window: {len(encoded)}")
    expected = render(encoded)
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            raise RuntimeError(
                "companion Web gzip asset is stale; run "
                "tools/generate_companion_web_asset.py")
    else:
        OUTPUT.write_text(expected, encoding="utf-8")
    print(
        f"companion Web asset passed: {len(payload)} -> {len(encoded)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
