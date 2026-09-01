#!/usr/bin/env python3
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "tests/hil/evidence/"
            "board-01-wifi-security-advisor-1.0.0-dev.364.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    value = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    require(value.get("schema") ==
            "leshy.wifi_security_advisor_hil.acceptance.v1",
            "wrong Wi-Fi security advisor evidence schema")
    require(value.get("status") == "pass_wifi_security_advisor",
            "Wi-Fi security advisor evidence is not a pass")

    candidate = value.get("candidate", {})
    require(candidate.get("version") == "1.0.0-dev.364",
            "unexpected accepted firmware version")
    require(candidate.get("fresh_flashes") == 1,
            "acceptance must bind exactly one fresh flash")
    for key in ("app_elf_sha256", "factory_sha256", "firmware_sha256",
                "firmware_source_commit", "runner_source_sha256", "cid"):
        require(isinstance(candidate.get(key), str) and candidate[key],
                f"missing candidate provenance: {key}")

    verified = value.get("verified", {})
    exact_true = (
        "buzzer_inactive",
        "cleanup_complete",
        "cursor_not_reset_after_user_navigation",
        "live_order_remains_strongest_first",
        "passive_wifi_only",
        "plain_language_assessment_visible",
        "pmf_unknown_rendered_truthfully",
        "selected_identity_preserved_during_live_sort",
        "two_complete_wifi_lifecycles",
        "zero_heap_drift_after_warmup",
    )
    for key in exact_true:
        require(verified.get(key) is True, f"acceptance invariant failed: {key}")
    for key in ("advisor_chrome_changed_pixels",
                "advisor_content_changed_pixels", "detail_outside_signal_pixels",
                "final_lease_mask", "input_queue_drops", "manual_button_presses",
                "physical_storage_write_calls"):
        require(verified.get(key) == 0, f"acceptance counter is non-zero: {key}")
    require(verified.get("heap_free_after_first_lifecycle_bytes") ==
            verified.get("heap_free_after_second_lifecycle_bytes"),
            "post-warm heap drifted between lifecycles")
    require(verified.get("final_page") == "home" and
            verified.get("final_runtime_owner") == "none",
            "acceptance did not finish at clean Home")

    privacy = value.get("privacy", {})
    require(privacy == {
        "ambient_bssid_retained": False,
        "ambient_ssid_retained": False,
        "ambient_vendor_retained": False,
        "raw_run_retained": False,
        "screen_hashes_only": True,
    }, "privacy-minimal retention contract changed")
    forbidden_keys = {"ssid", "bssid", "vendor", "network_identity_hash"}
    seen = set()
    def visit(node: object) -> None:
        if isinstance(node, dict):
            seen.update(str(key).lower() for key in node)
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(value)
    require(not (seen & forbidden_keys),
            "retained evidence contains an ambient identity key")
    print("wifi_security_advisor_hil_acceptance: PASS")


if __name__ == "__main__":
    main()
