#!/usr/bin/env python3
"""Shared fail-closed heap policy for repeatable Wi-Fi lifecycles."""

from __future__ import annotations


# ESP-IDF performs bounded process-lifetime allocation on the first
# esp_wifi_init()/esp_wifi_deinit() lifecycle.  A cold exact-flash run on the
# no-PSRAM ESP32-DIV retained 7,344 bytes and then held an exact 59,320-byte
# plateau across the next complete lifecycle and an extended idle observation.
# Keep modest headroom above that measured cold-start cost while continuing to
# reject a growing plateau on every subsequent lifecycle.
MAX_ONE_TIME_WIFI_INITIALIZATION_BYTES = 8 * 1024


def wifi_heap_plateau_failures(
    boot_free: object,
    first_free: object,
    final_free: object,
    first_total: object,
    final_total: object,
) -> list[str]:
    """Return stable diagnostics for an invalid two-cycle heap plateau."""

    values = (boot_free, first_free, final_free, first_total, final_total)
    if not all(isinstance(value, int) and not isinstance(value, bool)
               for value in values):
        return ["heap measurements are incomplete"]

    failures: list[str] = []
    warmup_bytes = boot_free - first_free
    if (warmup_bytes < 0 or
            warmup_bytes > MAX_ONE_TIME_WIFI_INITIALIZATION_BYTES):
        failures.append(
            "Wi-Fi one-time heap initialization is unbounded: "
            f"{warmup_bytes} bytes")
    if final_free != first_free:
        failures.append("heap changed after the second complete Wi-Fi cycle")
    if final_total != first_total:
        failures.append("heap total changed between Wi-Fi cycles")
    return failures
