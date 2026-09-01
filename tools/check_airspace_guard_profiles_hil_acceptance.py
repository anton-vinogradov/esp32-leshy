#!/usr/bin/env python3
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "tests/hil/evidence/"
            "board-01-airspace-guard-profiles-1.0.0-dev.365.json")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(value.get("schema") ==
            "leshy.airspace_guard_profiles_hil.acceptance.v1",
            "wrong Airspace Guard profiles evidence schema")
    require(value.get("status") == "pass_airspace_guard_profiles",
            "Airspace Guard profiles evidence is not a pass")

    candidate = value.get("candidate", {})
    require(candidate.get("version") == "1.0.0-dev.365",
            "unexpected accepted firmware version")
    require(candidate.get("firmware_source_commit") ==
            "3e966f167b4f9e2facb3a57836f7ced1b2d46765",
            "unexpected accepted firmware source")
    require(candidate.get("fresh_flashes") == 1 and
            candidate.get("accepted_delta_reused_exact_flash") is True,
            "exact one-flash/delta lineage is not proved")
    for key in ("app_elf_sha256", "factory_sha256", "firmware_sha256",
                "map_sha256", "runner_source_sha256"):
        require(isinstance(candidate.get(key), str) and
                HEX64.fullmatch(candidate[key]) is not None,
                f"missing candidate provenance: {key}")

    verified = value.get("verified", {})
    for key in ("cleanup_complete", "passive_receive_only",
                "three_profile_cancels_checked",
                "three_profile_starts_checked",
                "visual_plain_language_review_passed"):
        require(verified.get(key) is True,
                f"acceptance invariant failed: {key}")
    for key in ("application_connect_calls", "application_raw_tx_calls",
                "final_lease_mask", "host_wifi_control_calls",
                "manual_button_presses", "physical_storage_write_calls",
                "profile_repaint_static_pixels"):
        require(verified.get(key) == 0,
                f"acceptance counter is non-zero: {key}")
    require(verified.get("profiles_checked") == 3 and
            verified.get("profile_starts_checked") == 3,
            "all three profiles were not selected and started")
    require(verified.get("final_page") == "home" and
            verified.get("final_runtime_owner") == "none" and
            verified.get("final_hil_session_active") is False,
            "acceptance did not finish at clean Home with HIL inactive")
    require(verified.get("full_airspace_guard_release_gate_claimed") is False,
            "profile delta must not claim the full release gate")
    require(verified.get("profile_repaint_changed_pixels", 0) > 0,
            "profile selection did not visibly repaint")
    require(verified.get("profile_policies") == {
        "busy_place": {
            "ble_tracker_threshold": 5, "churn_threshold": 6,
            "disconnect_threshold": 6, "noise_floor_dbm": -70,
            "noise_threshold": 6, "selection": 2,
        },
        "everyday": {
            "ble_tracker_threshold": 3, "churn_threshold": 4,
            "disconnect_threshold": 4, "noise_floor_dbm": -75,
            "noise_threshold": 4, "selection": 0,
        },
        "quiet_place": {
            "ble_tracker_threshold": 3, "churn_threshold": 3,
            "disconnect_threshold": 3, "noise_floor_dbm": -80,
            "noise_threshold": 3, "selection": 1,
        },
    }, "accepted profile policies changed")
    for digest in verified.get("screen_hashes", {}).values():
        require(isinstance(digest, str) and HEX64.fullmatch(digest) is not None,
                "invalid retained screen hash")
    require(len(verified.get("screen_hashes", {})) == 6,
            "all three PNG/RGB565 screen pairs are not bound")

    precursor = value.get("precursor", {})
    require(precursor.get("accepted") is False and
            precursor.get("status") == "failed_full_gate" and
            precursor.get("failure") ==
            "two lifecycle gate has no conclusive lifecycle" and
            precursor.get("first_exact_malformed_wifi_frames") == 6 and
            precursor.get("second_exact_capacity_drops") == 887,
            "fail-closed full-gate precursor is not retained honestly")

    require(value.get("privacy") == {
        "ambient_bssid_retained": False,
        "ambient_ssid_retained": False,
        "ambient_vendor_retained": False,
        "raw_run_retained": False,
        "screen_hashes_only": True,
    }, "privacy-minimal retention contract changed")
    forbidden = {"ssid", "bssid", "vendor", "network_identity_hash"}
    seen: set[str] = set()
    def visit(node: object) -> None:
        if isinstance(node, dict):
            seen.update(str(key).lower() for key in node)
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(value)
    require(not (seen & forbidden),
            "retained evidence contains an ambient identity key")
    print("airspace_guard_profiles_hil_acceptance: PASS")


if __name__ == "__main__":
    main()
