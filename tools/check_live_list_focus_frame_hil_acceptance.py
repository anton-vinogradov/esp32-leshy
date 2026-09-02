#!/usr/bin/env python3
"""Validate the privacy-minimal physical live-list focus-frame evidence."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "tests/hil/evidence/"
            "board-01-live-list-focus-frame-1.0.0-dev.372.json")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def require_hash(value: object, label: str) -> None:
    require(isinstance(value, str) and HEX64.fullmatch(value) is not None,
            f"invalid SHA-256: {label}")


def main() -> None:
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(value.get("schema") ==
            "leshy.live_list_focus_frame_hil.acceptance.v1",
            "wrong live-list focus-frame evidence schema")
    require(value.get("status") == "pass_live_list_focus_frame",
            "live-list focus frame is not accepted")
    require(value.get("board") == "board-01", "unexpected board")
    require(value.get("evidence_ids") == [
        "E-BUILD-242", "E-AUTO-221", "E-HIL-239", "E-UX-091", "RB-M255"
    ], "unexpected evidence IDs")

    candidate = value.get("candidate", {})
    require(candidate.get("version") == "1.0.0-dev.372" and
            candidate.get("cid") == "FE343253440000002000000055019CB7" and
            candidate.get("firmware_bytes") == 3661200 and
            candidate.get("factory_bytes") == 3726736 and
            candidate.get("elf_bytes") == 25339920 and
            candidate.get("fresh_flashes") == 1 and
            candidate.get("exact_image_reuse_runs") == 2,
            "candidate identity/size/flash accounting changed")
    for key in ("render_fix_commit", "accepted_source_commit"):
        require(isinstance(candidate.get(key), str) and
                HEX40.fullmatch(candidate[key]) is not None,
                f"invalid source commit: candidate.{key}")
    for key in ("firmware_sha256", "factory_sha256", "elf_sha256",
                "map_sha256"):
        require_hash(candidate.get(key), f"candidate.{key}")

    tooling = value.get("host_tooling", {})
    for key in ("runner_sha256", "run_checker_sha256",
                "render_contract_checker_sha256"):
        require_hash(tooling.get(key), f"host_tooling.{key}")
    require(tooling.get("daemon_or_service_installed") is False,
            "unexpected host service")

    accepted = value.get("accepted_run", {})
    require_hash(accepted.get("run_sha256"), "accepted_run.run_sha256")
    require(accepted.get("passed") is True and
            accepted.get("gate_eligible") is True and
            accepted.get("flash_mode") == "reuse_exact" and
            accepted.get("wifi_lifecycles") == 2 and
            accepted.get("navigation_presses") == 8 and
            accepted.get("maximum_unique_networks") == 25 and
            accepted.get("manual_button_presses") == 0,
            "accepted physical journey changed")

    rendering = value.get("rendering", {})
    require(rendering.get("shared_lists") == [
        "wifi_networks", "wifi_devices", "ble_devices"
    ], "shared live-list coverage changed")
    require(rendering.get("selection_overlay_composited_last") is True and
            rendering.get("first_focus_frame_continuous") is True and
            rendering.get("second_focus_frame_continuous") is True and
            rendering.get("focus_frame_mismatches") == 0 and
            rendering.get("focus_distinct_from_background") is True and
            rendering.get("list_content_changed_pixels") == 667 and
            rendering.get("list_chrome_changed_pixels") == 0 and
            rendering.get("detail_signal_card_changed_pixels") == 55 and
            rendering.get("detail_chrome_changed_pixels") == 0 and
            rendering.get("detail_outside_signal_card_changed_pixels") == 0 and
            rendering.get("live_order_strongest_first") is True and
            rendering.get("selected_identity_preserved") is True and
            rendering.get("cursor_reset_after_user_navigation") is False,
            "focus-frame or bounded repaint result changed")

    require(value.get("runtime") == {
        "first_heap_total_bytes": 143428,
        "first_heap_free_bytes": 60512,
        "first_heap_min_free_bytes": 18896,
        "second_heap_total_bytes": 143428,
        "second_heap_free_bytes": 60512,
        "second_heap_min_free_bytes": 18896,
        "heap_drift_after_warmup_bytes": 0,
        "input_queue_drops": 0,
        "input_read_errors": 0,
        "ambiguous_presses": 0,
        "wifi_driver_drops_during_list_capture": 0,
    }, "runtime accounting changed")
    require(value.get("storage") == {
        "generation": 13,
        "mounted_read_only": True,
        "store_open_attempted_during_live_list": False,
        "physical_write_calls": 0,
        "blocked_write_attempts": 0,
        "cleanup_complete": True,
    }, "read-only storage boundary changed")
    require(value.get("policy") == {
        "passive_wifi_only": True,
        "host_network_tools_invoked": False,
        "active_host_wifi_touched": False,
        "raw_radio_tx_commands_invoked_by_runner": 0,
        "instrumented_rf_silence_claimed": False,
        "buzzer_inactive": True,
        "nrf_ce_inactive": True,
        "software_quiesce_complete": True,
    }, "host/network/radio policy changed")
    require(value.get("cleanup") == {
        "complete": True,
        "final_page": "home",
        "final_runtime_owner": "none",
        "final_lease_mask": 0,
    }, "final cleanup changed")

    precursors = value.get("precursors", [])
    require(len(precursors) == 2, "expected two honest fail-closed precursors")
    expected_reasons = (
        "stale oracle expected a store open during the read-only live list",
        "stale oracle expected a static detail screen instead of the bounded live signal card",
    )
    for index, precursor in enumerate(precursors):
        require_hash(precursor.get("run_sha256"),
                     f"precursors[{index}].run_sha256")
        require(isinstance(precursor.get("source_commit"), str) and
                HEX40.fullmatch(precursor["source_commit"]) is not None,
                f"invalid precursor source commit: {index}")
        require(precursor.get("accepted") is False and
                precursor.get("reason") == expected_reasons[index] and
                precursor.get("cleanup_complete") is True and
                precursor.get("final_page") == "home" and
                precursor.get("final_runtime_owner") == "none" and
                precursor.get("final_lease_mask") == 0,
                f"precursor boundary changed: {index}")

    require(value.get("privacy") == {
        "ambient_identifiers_retained": False,
        "raw_run_retained": False,
        "screenshots_retained": False,
        "exact_device_port_retained": False,
    }, "privacy-minimal retention changed")
    require(value.get("resources") == {
        "static_ram_bytes": 235376,
        "linked_flash_bytes": 3660700,
        "application_image_bytes": 3661200,
        "factory_image_bytes": 3726736,
        "free_ota_bytes": 533104,
        "required_free_ota_bytes": 524288,
    }, "resource bound changed")
    print("live_list_focus_frame_hil_acceptance: PASS")


if __name__ == "__main__":
    main()
