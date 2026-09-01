#!/usr/bin/env python3
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "tests/hil/evidence/"
            "board-01-wifi-own-identity-1.0.0-dev.369.json")
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
            "leshy.wifi_own_identity_hil.acceptance.v1",
            "wrong Wi-Fi own-identity evidence schema")
    require(value.get("status") == "pass_wifi_own_identity",
            "Wi-Fi own identity is not accepted")
    require(value.get("board") == "board-01", "unexpected board")
    require(value.get("evidence_ids") == [
        "E-BUILD-241", "E-AUTO-219", "E-HIL-237", "RB-M253"
    ], "unexpected evidence IDs")

    candidate = value.get("candidate", {})
    require(candidate.get("version") == "1.0.0-dev.369" and
            candidate.get("cid") == "FE343253440000002000000055019CB7" and
            candidate.get("fresh_flashes") == 1 and
            candidate.get("firmware_bytes") == 3656896 and
            candidate.get("factory_bytes") == 3722432,
            "candidate identity/size changed")
    for key in ("firmware_source_commit", "runner_source_commit"):
        require(isinstance(candidate.get(key), str) and
                HEX40.fullmatch(candidate[key]) is not None,
                f"invalid source commit: candidate.{key}")
    for key in ("firmware_sha256", "factory_sha256", "elf_sha256",
                "map_sha256"):
        require_hash(candidate.get(key), f"candidate.{key}")

    tooling = value.get("host_tooling", {})
    require_hash(tooling.get("runner_sha256"), "host_tooling.runner_sha256")
    require_hash(tooling.get("contract_checker_sha256"),
                 "host_tooling.contract_checker_sha256")
    require(tooling.get("external_serial_dependency") is True and
            tooling.get("daemon_or_service_installed") is False,
            "host-tooling boundary changed")

    run = value.get("accepted_run", {})
    require_hash(run.get("run_sha256"), "accepted_run.run_sha256")
    require(run == {
        "run_sha256": run.get("run_sha256"),
        "status": "pass",
        "flash_count": 1,
        "ports_opened": 1,
        "clone_ports_opened": 0,
        "cardputer_ports_opened": 0,
        "final_page": "home",
        "final_runtime_owner": "none",
        "final_lease_mask": 0,
    }, "accepted-run boundary changed")

    require(value.get("journey") == {
        "device_connection_index": 2,
        "identity_privacy_view": 3,
        "hardware_opt_out_selected": True,
        "private_mode_restored": True,
        "passive_receiver_sessions": 2,
        "cleanup_before_first_complete": True,
        "cleanup_between_complete": True,
        "cleanup_final_complete": True,
    }, "identity journey changed")
    require(value.get("identity_policy") == {
        "default_mode": "private_per_session",
        "scope": "own_station_and_temporary_wifi",
        "persisted_value": "mode_only",
        "hardware_mode_provenance": "hardware",
        "private_mode_provenance": "generated_private_session",
        "first_generation": 1,
        "second_generation": 2,
        "first_station_applications": 1,
        "second_station_applications": 2,
        "local_admin": True,
        "unicast": True,
        "differs_from_hardware": True,
        "nearby_identity_modified": False,
        "raw_address_retained": False,
        "failures": 0,
        "last_error": 0,
    }, "own-identity policy changed")
    require(value.get("storage_recovery") == {
        "generation": 10,
        "observations": 51,
        "exact_cid_matched": True,
        "mounted_read_only": True,
        "physical_write_calls": 0,
        "blocked_write_attempts": 0,
        "cleanup_complete": True,
    }, "read-only storage recovery changed")
    require(value.get("protected_ui_admission") == {
        "begun": True,
        "ram_only": True,
        "protected_ui_only": True,
        "credential_written": False,
        "whole_nvs_read_or_copied": False,
        "product_namespace_written_or_erased": False,
        "cleanup_proven": True,
        "active_at_end": False,
    }, "protected HIL admission changed")
    require(value.get("policy") == {
        "wifi_softap_started": False,
        "host_network_tools_invoked": False,
        "active_host_wifi_touched": False,
        "raw_radio_tx_commands": 0,
        "buzzer_inactive": True,
        "nrf_ce_inactive": True,
        "software_quiesce_complete": True,
    }, "network/radio/safe-output boundary changed")

    precursor = value.get("precursor", {})
    require_hash(precursor.get("run_sha256"), "precursor.run_sha256")
    require(precursor == {
        "accepted": False,
        "run_sha256": precursor.get("run_sha256"),
        "source_commit": "fa55cd1aeb78cc921e40879f2708e7870ccc351a",
        "reason": "host sandbox denied opening the serial device before flashing",
        "device_access_succeeded": False,
        "flash_started": False,
        "product_navigation_started": False,
        "wifi_softap_started": False,
        "active_host_wifi_touched": False,
        "raw_radio_tx_commands": 0,
    }, "honest precursor boundary changed")
    require(value.get("privacy") == {
        "own_raw_addresses_retained": False,
        "ambient_identifiers_retained": False,
        "credentials_retained": False,
        "raw_run_retained": False,
        "screenshots_retained": False,
        "exact_device_port_retained": False,
    }, "privacy-minimal retention changed")
    require(value.get("resources") == {
        "static_ram_bytes": 235000,
        "linked_flash_bytes": 3656388,
        "application_image_bytes": 3656896,
        "factory_image_bytes": 3722432,
        "free_ota_bytes": 537408,
        "required_free_ota_bytes": 524288,
        "boot_heap_total_bytes": 143804,
        "boot_heap_free_bytes": 69448,
        "boot_heap_min_free_bytes": 69300,
    }, "Wi-Fi own-identity resource bound changed")
    print("wifi_own_identity_hil_acceptance: PASS")


if __name__ == "__main__":
    main()
