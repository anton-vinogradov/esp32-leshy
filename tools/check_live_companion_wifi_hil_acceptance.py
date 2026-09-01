#!/usr/bin/env python3
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "tests/hil/evidence/"
            "board-01-live-companion-wifi-1.0.0-dev.367.json")
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
            "leshy.live_companion_wifi_hil.acceptance.v1",
            "wrong Live Companion Wi-Fi evidence schema")
    require(value.get("status") == "pass_live_companion_wifi",
            "Live Companion Wi-Fi evidence is not a pass")
    require(value.get("board") == "board-01", "unexpected board")

    candidate = value.get("candidate", {})
    require(candidate.get("version") == "1.0.0-dev.367",
            "unexpected Live Companion candidate version")
    require(candidate.get("cid") == "FE343253440000002000000055019CB7",
            "unexpected Live Companion media identity")
    require(candidate.get("fresh_flashes") == 1 and
            candidate.get("accepted_run_exact_flash_reused") is True,
            "single-flash lineage changed")
    for key in ("firmware_source_commit", "accepted_runner_source_commit"):
        require(isinstance(candidate.get(key), str) and
                HEX40.fullmatch(candidate[key]) is not None,
                f"invalid source commit: candidate.{key}")
    for key in ("firmware_sha256", "factory_sha256", "elf_sha256",
                "map_sha256"):
        require_hash(candidate.get(key), f"candidate.{key}")
    require(candidate.get("firmware_bytes") == 3649760 and
            candidate.get("factory_bytes") == 3715296,
            "candidate size changed")

    tooling = value.get("host_tooling", {})
    for key in ("runner_sha256", "extcap_sha256", "installer_sha256"):
        require_hash(tooling.get(key), f"host_tooling.{key}")
    require(tooling.get("external_serial_dependency") is False and
            tooling.get("daemon_or_service_installed") is False and
            tooling.get("wireshark_executable") == "tshark",
            "host tooling boundary changed")

    accepted = value.get("accepted_run", {})
    require(accepted.get("status") == "pass" and
            accepted.get("cleanup_complete") is True and
            accepted.get("final_page") == "home" and
            accepted.get("final_runtime_owner") == "none" and
            accepted.get("final_lease_mask") == 0,
            "accepted run did not finish cleanly")
    require(accepted.get("ports_opened") == 1 and
            accepted.get("serial_port_discovery_calls") == 0 and
            accepted.get("clone_ports_opened") == 0 and
            accepted.get("cardputer_ports_opened") == 0,
            "accepted run widened its device boundary")
    require_hash(accepted.get("run_sha256"), "accepted_run.run_sha256")
    require_hash(accepted.get("artifact_index_sha256"),
                 "accepted_run.artifact_index_sha256")

    recovery = value.get("storage_recovery", {})
    require(recovery == {
        "generation": 10,
        "observations": 51,
        "exact_cid_matched": True,
        "mounted_read_only": True,
        "physical_write_calls": 0,
        "blocked_write_attempts": 0,
        "cleanup_complete": True,
    }, "read-only exact-CID recovery changed")

    live = value.get("live_stream", {})
    require(live.get("connect_scopes") == ["capture.live.read"] and
            live.get("granted_capabilities") == ["capture.live.wifi"],
            "Live Companion grant widened")
    require(live.get("requests") == 194 and
            live.get("read_requests") == 193 and
            live.get("stream_bytes") == 4076 and
            live.get("frames") == 16 and
            live.get("dropped_capacity") == 269 and
            live.get("dropped_invalid") == 0,
            "bounded stream accounting changed")
    require(live.get("driver_error") == 0 and
            live.get("duration_ms") == 10000 and
            live.get("maximum_frames") == 16 and
            live.get("snap_length") == 256 and
            live.get("passive_only") is True and
            live.get("rx_only") is True and
            live.get("storage_written") is False and
            live.get("cleanup_complete") is True and
            live.get("application_connect_calls") == 0 and
            live.get("application_raw_tx_calls") == 0,
            "capture safety/accounting invariant changed")
    pcap = live.get("pcap", {})
    require_hash(pcap.get("sha256"), "live_stream.pcap.sha256")
    require(pcap.get("bytes") == 4076 and
            pcap.get("records") == 16 and
            pcap.get("linktype") == 127 and
            pcap.get("version") == "2.4" and
            pcap.get("snaplen") == 271 and
            pcap.get("captured_frame_bytes") == 3556 and
            pcap.get("original_frame_bytes") == 4287 and
            pcap.get("fcs_included_records") == 8 and
            pcap.get("management_frames") == 14 and
            pcap.get("data_frames") == 2 and
            pcap.get("frequencies_mhz") == [2412, 2422, 2427, 2432] and
            pcap.get("rssi_min_dbm") == -87 and
            pcap.get("rssi_max_dbm") == -71,
            "PCAP summary changed")
    require(live.get("wireshark") == {
        "accepted": True, "records": 16, "stderr_empty": True,
    }, "Wireshark did not accept the exact stream")

    terminal = value.get("terminal_state", {})
    require(terminal == {
        "capture_state": "idle",
        "frames_accepted": 0,
        "frames_reported": 0,
        "payload_bytes": 0,
        "pcap_available": False,
        "lease_mask": 0,
        "software_quiesce_complete": True,
        "buzzer_inactive": True,
        "nrf_ce_inactive": True,
        "input_status": "ready",
        "input_queue_drops": 0,
        "input_read_errors": 0,
    }, "terminal cleanup/safety state changed")
    require(value.get("policy") == {
        "read_only_companion": True,
        "capture_started_only_by_user_ui_action": True,
        "companion_radio_start_commands": 0,
        "companion_radio_stop_commands": 0,
        "companion_tx_commands": 0,
        "storage_writes_requested": 0,
        "host_network_tools_invoked": False,
        "active_host_wifi_touched": False,
        "host_ble_advertising_started": False,
        "physical_no_tx_claimed": False,
    }, "host/radio policy changed")

    screens = value.get("screens", {})
    require(len(screens) == 10, "all five screen pairs are not bound")
    for key, digest in screens.items():
        require_hash(digest, f"screens.{key}")
    require(value.get("visual_plain_language_review_passed") is True,
            "plain-language TFT review is not accepted")

    precursors = value.get("precursors", {})
    require(set(precursors) == {"flash_handshake", "mixed_fcs_oracle",
                                "safe_output_schema_oracle",
                                "input_schema_oracle"},
            "precursor set changed")
    for key, precursor in precursors.items():
        require(precursor.get("accepted") is False,
                f"precursor unexpectedly accepted: {key}")
        require_hash(precursor.get("run_sha256"), f"precursors.{key}.run")
    require(precursors["flash_handshake"].get("device_actions_started") is False,
            "flash-handshake precursor touched the product path")
    for key in ("mixed_fcs_oracle", "safe_output_schema_oracle",
                "input_schema_oracle"):
        require(precursors[key].get("product_stream_complete") is True and
                precursors[key].get("cleanup_complete") is True,
                f"product path/cleanup not proven in {key}")

    require(value.get("privacy") == {
        "ambient_identifiers_retained": False,
        "raw_80211_payload_retained": False,
        "raw_pcap_retained": False,
        "raw_run_retained": False,
        "screenshots_retained": False,
        "screen_hashes_only": True,
        "retained_pcap_material": "hash_counts_channel_rssi_bounds_only",
    }, "privacy-minimal retention contract changed")
    resources = value.get("resources", {})
    require(resources == {
        "static_ram_bytes": 234976,
        "linked_flash_bytes": 3649260,
        "application_image_bytes": 3649760,
        "factory_image_bytes": 3715296,
        "free_ota_bytes": 544544,
        "required_free_ota_bytes": 524288,
        "boot_heap_total_bytes": 143828,
        "boot_heap_free_bytes": 68844,
        "boot_heap_min_free_bytes": 25340,
    }, "Live Companion resource bound changed")
    print("live_companion_wifi_hil_acceptance: PASS")


if __name__ == "__main__":
    main()
