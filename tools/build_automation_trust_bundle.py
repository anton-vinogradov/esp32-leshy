#!/usr/bin/env python3
"""Build a public-only LHAK v1 enrollment bundle from a P-256 public key."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import struct
import zlib
from pathlib import Path


BUNDLE_BYTES = 128
LABEL_BYTES = 24


def der_item(data: bytes, offset: int) -> tuple[int, bytes, int]:
    if offset >= len(data):
        raise ValueError("truncated DER tag")
    tag = data[offset]
    offset += 1
    if offset >= len(data):
        raise ValueError("truncated DER length")
    first = data[offset]
    offset += 1
    if first & 0x80:
        count = first & 0x7F
        if count == 0 or count > 4 or offset + count > len(data):
            raise ValueError("invalid DER length")
        length = int.from_bytes(data[offset : offset + count], "big")
        offset += count
    else:
        length = first
    end = offset + length
    if end > len(data):
        raise ValueError("truncated DER value")
    return tag, data[offset:end], end


def read_spki_p256(path: Path) -> bytes:
    text = path.read_text(encoding="ascii")
    begin = "-----BEGIN PUBLIC KEY-----"
    end = "-----END PUBLIC KEY-----"
    if begin not in text or end not in text:
        raise ValueError("expected SubjectPublicKeyInfo PUBLIC KEY PEM")
    payload = text.split(begin, 1)[1].split(end, 1)[0]
    der = base64.b64decode("".join(payload.split()), validate=True)
    tag, sequence, consumed = der_item(der, 0)
    if tag != 0x30 or consumed != len(der):
        raise ValueError("invalid SubjectPublicKeyInfo sequence")
    algorithm_tag, algorithm, cursor = der_item(sequence, 0)
    if algorithm_tag != 0x30:
        raise ValueError("missing public-key algorithm")
    oid_tag, algorithm_oid, algorithm_cursor = der_item(algorithm, 0)
    curve_tag, curve_oid, algorithm_end = der_item(algorithm, algorithm_cursor)
    # id-ecPublicKey 1.2.840.10045.2.1 and prime256v1 1.2.840.10045.3.1.7
    if (
        oid_tag != 0x06
        or algorithm_oid != bytes.fromhex("2a8648ce3d0201")
        or curve_tag != 0x06
        or curve_oid != bytes.fromhex("2a8648ce3d030107")
        or algorithm_end != len(algorithm)
    ):
        raise ValueError("only P-256 SubjectPublicKeyInfo is accepted")
    point_tag, point_bits, cursor = der_item(sequence, cursor)
    if point_tag != 0x03 or cursor != len(sequence) or len(point_bits) != 66:
        raise ValueError("invalid P-256 public point")
    if point_bits[0] != 0 or point_bits[1] != 0x04:
        raise ValueError("compressed/noncanonical P-256 point is forbidden")
    return point_bits[1:]


def build_bundle(public_key: bytes, label: str) -> tuple[bytes, dict[str, object]]:
    encoded_label = label.encode("ascii")
    if not encoded_label or len(encoded_label) > LABEL_BYTES:
        raise ValueError("label must contain 1..24 printable ASCII bytes")
    if any(byte < 0x20 or byte > 0x7E for byte in encoded_label):
        raise ValueError("label must contain printable ASCII only")
    if len(public_key) != 65 or public_key[0] != 0x04:
        raise ValueError("expected uncompressed SEC1 P-256 public point")
    key_digest = hashlib.sha256(public_key).digest()
    key_id = key_digest[:8]
    bundle = bytearray(BUNDLE_BYTES)
    struct.pack_into("<4sBBH", bundle, 0, b"LHAK", 1, 1, BUNDLE_BYTES)
    bundle[8:16] = key_id
    bundle[16:81] = public_key
    bundle[81 : 81 + len(encoded_label)] = encoded_label
    struct.pack_into("<I", bundle, 124, zlib.crc32(bundle[:124]) & 0xFFFFFFFF)
    result = bytes(bundle)
    metadata: dict[str, object] = {
        "schema": "leshy.automation.trust_bundle.v1",
        "algorithm": "ecdsa_p256_sha256",
        "label": label,
        "key_id": key_id.hex(),
        "public_key_sha256": key_digest.hex(),
        "bundle_bytes": len(result),
        "bundle_sha256": hashlib.sha256(result).hexdigest(),
        "contains_private_key": False,
    }
    return result, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()
    public_key = read_spki_p256(args.public_key)
    bundle, metadata = build_bundle(public_key, args.label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bundle)
    if args.metadata is not None:
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
