#!/usr/bin/env python3
"""Fail-closed validation for the reviewed Leshy 1.x partition layout."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any


PARTITION_TABLE_OFFSET = 0x8000
PARTITION_TABLE_SIZE = 0x1000
PARTITION_ARTIFACT_SIZE = 0xC00
PARTITION_MAGIC = 0x50AA
PARTITION_MD5_MAGIC = 0xEBEB
APP0_OFFSET = 0x10000
APP0_SIZE = 0x400000
OTA1_OFFSET = 0x410000
OTA1_SIZE = 0x400000


def canonical_partition_table(path: Path) -> bytes:
    """Return an esptool-sized partition-table sector or fail closed."""
    payload = path.read_bytes()
    if len(payload) not in (PARTITION_ARTIFACT_SIZE, PARTITION_TABLE_SIZE):
        raise ValueError(
            f"partition table size {len(payload)} is not a reviewed artifact")
    return payload.ljust(PARTITION_TABLE_SIZE, b"\xff")


def validated_partition_layout(
    path: Path, firmware_size: int,
) -> dict[str, dict[str, int]]:
    """Require the reviewed 16 MB app0/app1 layout and a fitting image."""
    payload = canonical_partition_table(path)
    entries: dict[str, dict[str, int]] = {}
    md5_verified = False
    for offset in range(0, len(payload), 32):
        block = payload[offset:offset + 32]
        magic, kind, subtype, address, size, raw_label, flags = struct.unpack(
            "<HBBLL16sL", block)
        if magic == 0xFFFF:
            break
        if magic == PARTITION_MD5_MAGIC:
            expected_md5 = block[16:32]
            observed_md5 = hashlib.md5(payload[:offset]).digest()
            if expected_md5 != observed_md5:
                raise ValueError("partition table MD5 record does not match")
            md5_verified = True
            break
        if magic != PARTITION_MAGIC:
            raise ValueError(f"invalid partition magic at {offset:#x}")
        label = raw_label.split(b"\0", 1)[0].decode("ascii")
        if label in entries:
            raise ValueError(f"duplicate partition label: {label}")
        entries[label] = {
            "type": kind,
            "subtype": subtype,
            "offset": address,
            "size": size,
            "flags": flags,
        }
    if not md5_verified:
        raise ValueError("partition table has no verified MD5 record")

    expected = {
        "app0": {
            "type": 0, "subtype": 0x10, "offset": APP0_OFFSET,
            "size": APP0_SIZE, "flags": 0,
        },
        "app1": {
            "type": 0, "subtype": 0x11, "offset": OTA1_OFFSET,
            "size": OTA1_SIZE, "flags": 0,
        },
        "spiffs": {
            "type": 1, "subtype": 0x82, "offset": 0x810000,
            "size": 0x7D0000, "flags": 0,
        },
    }
    for label, wanted in expected.items():
        if entries.get(label) != wanted:
            raise ValueError(
                f"unsafe Leshy 1.x partition {label}: "
                f"{entries.get(label)} != {wanted}")
    if firmware_size > entries["app0"]["size"]:
        raise ValueError(
            f"candidate firmware {firmware_size} does not fit app0 "
            f"{entries['app0']['size']}")
    app0_end = entries["app0"]["offset"] + entries["app0"]["size"]
    if app0_end != entries["app1"]["offset"]:
        raise ValueError("Leshy 1.x app0/app1 boundary is not exact")
    return entries
