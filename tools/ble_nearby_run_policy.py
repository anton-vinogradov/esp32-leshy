#!/usr/bin/env python3
"""Truthful evidence scope for the direct Bluetooth Nearby HIL gate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def boot_recovery_continuity(before: Mapping[str, Any],
                             after: Mapping[str, Any]) -> bool:
    """Prove only the boot-recovery fields observed at both checkpoints."""
    for key in ("generation", "observations"):
        before_value = before.get(key)
        after_value = after.get(key)
        if (not isinstance(before_value, int) or
                isinstance(before_value, bool) or
                not isinstance(after_value, int) or
                isinstance(after_value, bool) or
                before_value != after_value):
            return False
    return True


def storage_measurement_scope_valid(scope: Mapping[str, Any]) -> bool:
    """Reject claims that this HIL gate did not globally measure."""
    return (
        scope.get("boot_recovery_continuity") is True and
        scope.get("product_storage_writes_measured") is False and
        "storage_write_authorized" not in scope
    )


def display_signal_signature(state: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return only BLE signal values that can change rendered radar pixels.

    The UI prints exact current/minimum/maximum RSSI, but reduces the numerical
    trend to approaching (>= +4 dB), steady, or receding (<= -4 dB). Treating
    +1 -> 0 as a visual transition makes a byte-identical, correctly stable TFT
    frame fail the HIL oracle before a genuinely visible update arrives.
    """
    trend = state.get("rssi_trend_db")
    if not isinstance(trend, int) or isinstance(trend, bool):
        trend_bucket: int | None = None
    elif trend >= 4:
        trend_bucket = 1
    elif trend <= -4:
        trend_bucket = -1
    else:
        trend_bucket = 0
    return (
        state.get("rssi_dbm"),
        state.get("minimum_rssi_dbm"),
        state.get("maximum_rssi_dbm"),
        trend_bucket,
    )


def bounded_pipeline_accounting_valid(state: Mapping[str, Any]) -> bool:
    """Accept bounded retention loss only when it is explicit and exact."""
    values: list[int] = []
    for field in ("survey_received", "survey_forwarded", "survey_dropped",
                  "survey_queue_depth"):
        value = state.get(field)
        if (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            return False
        values.append(value)
    received, forwarded, dropped, queue_depth = values
    return received == forwarded + dropped and queue_depth == 0


def bounded_list_repaint_accounting_valid(
        before: Mapping[str, Any], after: Mapping[str, Any],
        content_changed_pixels: Any, maximum_row_repaints: int = 8) -> bool:
    """Allow a complete row only when strongest-first sorting moved identity."""
    fields = (
        "list_row_repaints", "list_row_full_repaints",
        "list_identity_replacements", "list_signal_delta_repaints",
        "list_atomic_note_pushes",
    )
    deltas: dict[str, int] = {}
    for field in fields:
        old = before.get(field)
        new = after.get(field)
        if (not isinstance(old, int) or isinstance(old, bool) or
                not isinstance(new, int) or isinstance(new, bool) or
                new < old):
            return False
        deltas[field] = new - old
    if (not isinstance(content_changed_pixels, int) or
            isinstance(content_changed_pixels, bool) or
            content_changed_pixels < 0 or maximum_row_repaints < 1):
        return False
    rows = deltas["list_row_repaints"]
    full = deltas["list_row_full_repaints"]
    replacements = deltas["list_identity_replacements"]
    signal = deltas["list_signal_delta_repaints"]
    atomic_notes = deltas["list_atomic_note_pushes"]
    visible_change_matches = (
        content_changed_pixels == 0 and rows == 0
    ) or (
        content_changed_pixels > 0 and 1 <= rows <= maximum_row_repaints
    )
    return (
        visible_change_matches and
        rows == full + signal and
        full == replacements and
        atomic_notes == rows
    )
