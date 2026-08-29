#!/usr/bin/env python3
"""Pure, PII-free state policy for the Bluetooth product-entry HIL gate."""

from __future__ import annotations

from typing import Any


# Match the firmware's complete bounded observer lifecycle: NimBLE host sync,
# the maximum two-attempt passive scan, host shutdown, and host/serial jitter.
NIMBLE_SYNC_TIMEOUT_MS = 5000
BLE_HOST_SHUTDOWN_TIMEOUT_MS = 2000
BLE_SCAN_RETRY_BUDGET_MS = 6100
BLE_ENTRY_STABILITY_MARGIN_MS = 1900
BLE_ENTRY_STABILITY_MINIMUM_MS = (
    NIMBLE_SYNC_TIMEOUT_MS +
    BLE_HOST_SHUTDOWN_TIMEOUT_MS +
    BLE_SCAN_RETRY_BUDGET_MS +
    BLE_ENTRY_STABILITY_MARGIN_MS
)
BLE_ENTRY_STABILITY_SECONDS = BLE_ENTRY_STABILITY_MINIMUM_MS / 1000.0


def ble_entry_failure(state: dict[str, Any]) -> str | None:
    """Return a bounded reason when the BLE product route is no longer safe."""
    if state.get("page") != "survey":
        return "page_bounced"
    if state.get("ble_product_view") != "devices":
        return "devices_view_closed"
    if state.get("survey_product_admission_status") == "source_unavailable" or \
            state.get("survey_product_status") in {
                "source_unavailable", "scanner_cleanup_failed",
                "cleanup_failed",
            }:
        return (
            "receiver_unavailable:"
            f"stage={state.get('ble_begin_stage', 'missing')},"
            f"error={state.get('ble_begin_error', 'missing')},"
            f"heap_free_before={state.get('ble_begin_heap_free_before', 'missing')},"
            f"heap_free_after={state.get('ble_begin_heap_free_after', 'missing')},"
            f"heap_largest_before={state.get('ble_begin_heap_largest_before', 'missing')},"
            f"heap_largest_after={state.get('ble_begin_heap_largest_after', 'missing')}"
        )
    if state.get("runtime_owner") != "ble" or state.get("lease_mask") != 15:
        return "runtime_lease_released"
    return None


def ble_entry_stability_evidence_failure(
        evidence: dict[str, Any]) -> str | None:
    """Validate that retained evidence spans the complete BLE lifecycle."""
    duration_ms = evidence.get("duration_ms")
    samples = evidence.get("samples")
    if (not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or
            duration_ms < BLE_ENTRY_STABILITY_MINIMUM_MS or
            not isinstance(samples, int) or isinstance(samples, bool) or
            samples < 2):
        return "bounded_lifecycle_unproven"
    final_state = evidence.get("final_state")
    if not isinstance(final_state, dict):
        return "final_state_missing"
    return ble_entry_failure(final_state)
