#!/usr/bin/env python3
"""Host contract for the bounded, reset-safe ESP32-S3 HIL transport."""

from __future__ import annotations

import time

from capture_1x_ui import PassiveSerial


def main() -> int:
    device = PassiveSerial()
    if device.write_timeout != 1.0:
        raise AssertionError("PassiveSerial write timeout must be bounded")
    started = time.monotonic()
    device.flush()
    if time.monotonic() - started > 0.05:
        raise AssertionError("PassiveSerial flush must never wait for tcdrain")
    if device.is_open:
        raise AssertionError("host contract unexpectedly opened a device")
    print("passive serial transport: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
