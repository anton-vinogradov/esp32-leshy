#!/usr/bin/env python3
"""Focused tests for the Leshy 1.x RB-02 build budget gate."""

from __future__ import annotations

import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

if __package__:
    from . import check_1x_build_budget as CHECKER
    from .partition_safety import (
        APP0_SIZE,
        MAXIMUM_APP_IMAGE_SIZE,
        MINIMUM_APP_SLOT_FREE_BYTES,
    )
else:
    import check_1x_build_budget as CHECKER
    from partition_safety import (
        APP0_SIZE,
        MAXIMUM_APP_IMAGE_SIZE,
        MINIMUM_APP_SLOT_FREE_BYTES,
    )


def partition_artifact(app1_size: int = APP0_SIZE) -> bytes:
    entries = bytearray()
    for kind, subtype, offset, size, label in (
            (1, 0x02, 0x9000, 0x5000, "nvs"),
            (1, 0x00, 0xE000, 0x2000, "otadata"),
            (0, 0x10, 0x10000, APP0_SIZE, "app0"),
            (0, 0x11, 0x410000, app1_size, "app1"),
            (1, 0x82, 0x810000, 0x7D0000, "spiffs"),
            (1, 0x03, 0xFE0000, 0x20000, "coredump")):
        entries.extend(struct.pack(
            "<HBBLL16sL", 0x50AA, kind, subtype, offset, size,
            label.encode("ascii").ljust(16, b"\0"), 0))
    entries.extend(struct.pack(
        "<HBBLL16sL", 0xEBEB, 0xFF, 0xFF, 0xFFFFFFFF, 0xFFFFFFFF,
        b"\xff" * 16, 0xFFFFFFFF)[:16])
    entries.extend(hashlib.md5(entries[:-16]).digest())
    return bytes(entries).ljust(0xC00, b"\xff")


class BuildBudgetTests(unittest.TestCase):
    def write_fixture(self, root: Path, firmware_size: int,
                      app1_size: int = APP0_SIZE) -> tuple[Path, Path]:
        partitions = root / "partitions.bin"
        firmware = root / "firmware.bin"
        partitions.write_bytes(partition_artifact(app1_size))
        with firmware.open("wb") as stream:
            stream.truncate(firmware_size)
        return partitions, firmware

    def test_exact_12_5_percent_headroom_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            partitions, firmware = self.write_fixture(
                Path(directory), MAXIMUM_APP_IMAGE_SIZE)
            report = CHECKER.check_budget(partitions, firmware)
        self.assertEqual(MAXIMUM_APP_IMAGE_SIZE,
                         report["firmware_bytes"])
        self.assertEqual(MINIMUM_APP_SLOT_FREE_BYTES,
                         report["free_bytes"])

    def test_one_byte_over_budget_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            partitions, firmware = self.write_fixture(
                Path(directory), MAXIMUM_APP_IMAGE_SIZE + 1)
            with self.assertRaisesRegex(ValueError, "exceeds RB-02 maximum"):
                CHECKER.check_budget(partitions, firmware)

    def test_non_reviewed_app1_size_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            partitions, firmware = self.write_fixture(
                Path(directory), 1, APP0_SIZE - 1)
            with self.assertRaisesRegex(ValueError, "unsafe Leshy 1.x"):
                CHECKER.check_budget(partitions, firmware)


if __name__ == "__main__":
    unittest.main()
