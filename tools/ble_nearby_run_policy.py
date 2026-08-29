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
