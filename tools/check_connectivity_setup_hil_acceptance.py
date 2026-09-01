#!/usr/bin/env python3
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "tests/hil/evidence/"
            "board-01-connectivity-setup-1.0.0-dev.368.json")
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
            "leshy.connectivity_setup_hil.acceptance.v1",
            "wrong connectivity-setup evidence schema")
    require(value.get("status") == "pass_connectivity_setup",
            "connectivity setup is not accepted")
    require(value.get("board") == "board-01", "unexpected board")

    candidate = value.get("candidate", {})
    require(candidate.get("version") == "1.0.0-dev.368",
            "unexpected candidate version")
    require(candidate.get("cid") == "FE343253440000002000000055019CB7",
            "unexpected media identity")
    require(candidate.get("fresh_flashes") == 1,
            "connectivity delta must use one fresh flash")
    for key in ("firmware_source_commit", "runner_source_commit"):
        require(isinstance(candidate.get(key), str) and
                HEX40.fullmatch(candidate[key]) is not None,
                f"invalid source commit: candidate.{key}")
    for key in ("firmware_sha256", "factory_sha256", "elf_sha256",
                "map_sha256"):
        require_hash(candidate.get(key), f"candidate.{key}")
    require(candidate.get("firmware_bytes") == 3652816 and
            candidate.get("factory_bytes") == 3718352,
            "candidate size changed")

    tooling = value.get("host_tooling", {})
    require_hash(tooling.get("runner_sha256"), "host_tooling.runner_sha256")
    require(tooling.get("external_serial_dependency") is False and
            tooling.get("daemon_or_service_installed") is False,
            "host-tooling boundary changed")

    run = value.get("accepted_run", {})
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
    require_hash(run.get("run_sha256"), "accepted_run.run_sha256")

    require(value.get("journey") == {
        "device_menu_connection_index": 2,
        "connection_page": "connectivity",
        "connection_menu_view": 0,
        "usb_guide_view": 1,
        "temporary_wifi_selection": 1,
        "temporary_wifi_overlay_opened": True,
        "temporary_wifi_authorized": False,
        "temporary_wifi_server_active": False,
        "temporary_wifi_network_core_ready": False,
        "temporary_wifi_associated_stations": 0,
        "temporary_wifi_cleanup_complete": True,
    }, "connectivity journey changed")
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
        "usb_recommended": True,
        "temporary_wifi_requires_second_confirmation": True,
        "wifi_softap_started": False,
        "credential_created": False,
        "credential_exported": False,
        "survey_library_network_dependency_created": False,
        "host_network_tools_invoked": False,
        "active_host_wifi_touched": False,
        "raw_radio_tx_commands": 0,
    }, "offline/secret/radio boundary changed")

    precursor = value.get("precursor", {})
    require(precursor.get("accepted") is False and
            precursor.get("source_commit") ==
            "e086ce2ef04878d1ffadec17dfbbcef75b57eaa4" and
            precursor.get("product_navigation_started") is False and
            precursor.get("wifi_softap_started") is False and
            precursor.get("active_host_wifi_touched") is False and
            precursor.get("raw_radio_tx_commands") == 0,
            "honest precursor boundary changed")
    require_hash(precursor.get("run_sha256"), "precursor.run_sha256")
    require(value.get("privacy") == {
        "ambient_identifiers_retained": False,
        "credentials_retained": False,
        "raw_run_retained": False,
        "screenshots_retained": False,
        "exact_device_port_retained": False,
    }, "privacy-minimal retention changed")
    require(value.get("resources") == {
        "static_ram_bytes": 234976,
        "linked_flash_bytes": 3652316,
        "application_image_bytes": 3652816,
        "factory_image_bytes": 3718352,
        "free_ota_bytes": 541488,
        "required_free_ota_bytes": 524288,
        "boot_heap_total_bytes": 143828,
        "boot_heap_free_bytes": 69472,
        "boot_heap_min_free_bytes": 69324,
    }, "connectivity resource bound changed")
    print("connectivity_setup_hil_acceptance: PASS")


if __name__ == "__main__":
    main()
