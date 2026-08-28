#!/usr/bin/env python3
"""Fail closed unless a built Leshy 1.x app preserves RB-02 OTA headroom."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__:
    from .partition_safety import (
        APP0_SIZE,
        MAXIMUM_APP_IMAGE_SIZE,
        MINIMUM_APP_SLOT_FREE_BYTES,
        OTA1_SIZE,
        validated_partition_layout,
    )
else:
    from partition_safety import (
        APP0_SIZE,
        MAXIMUM_APP_IMAGE_SIZE,
        MINIMUM_APP_SLOT_FREE_BYTES,
        OTA1_SIZE,
        validated_partition_layout,
    )


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "firmware/leshy1/.pio/build/esp32-div-v2-clean"


def check_budget(partitions: Path, firmware: Path) -> dict[str, int]:
    if not firmware.is_file():
        raise ValueError(f"candidate firmware not found: {firmware}")
    firmware_size = firmware.stat().st_size
    layout = validated_partition_layout(partitions, firmware_size)
    if (layout["app0"]["size"] != APP0_SIZE or
            layout["app1"]["size"] != OTA1_SIZE):
        raise ValueError("reviewed app0/app1 4 MiB OTA slots are missing")
    return {
        "firmware_bytes": firmware_size,
        "maximum_firmware_bytes": MAXIMUM_APP_IMAGE_SIZE,
        "slot_bytes": APP0_SIZE,
        "free_bytes": APP0_SIZE - firmware_size,
        "required_free_bytes": MINIMUM_APP_SLOT_FREE_BYTES,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partitions", type=Path,
                        default=BUILD / "partitions.bin")
    parser.add_argument("--firmware", type=Path,
                        default=BUILD / "firmware.bin")
    args = parser.parse_args(argv)
    try:
        report = check_budget(args.partitions, args.firmware)
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "1.x build budget passed: "
        f"firmware {report['firmware_bytes']}/{report['slot_bytes']} B; "
        f"free {report['free_bytes']} B "
        f"(required {report['required_free_bytes']} B)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
