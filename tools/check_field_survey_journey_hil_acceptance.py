#!/usr/bin/env python3
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (ROOT / "tests/hil/evidence/"
            "board-01-field-survey-journey-1.0.0-dev.366.json")
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
            "leshy.field_survey_journey_hil.acceptance.v1",
            "wrong Field Survey journey evidence schema")
    require(value.get("status") == "pass_field_survey_journey",
            "Field Survey journey evidence is not a pass")

    candidate = value.get("candidate", {})
    require(candidate.get("version") == "1.0.0-dev.366",
            "unexpected Field Survey candidate version")
    require(candidate.get("cid") == "FE343253440000002000000055019CB7",
            "unexpected Field Survey media identity")
    require(candidate.get("fresh_flashes") == 1,
            "Field Survey candidate was not flashed exactly once")
    require(isinstance(candidate.get("firmware_source_commit"), str) and
            HEX40.fullmatch(candidate["firmware_source_commit"]) is not None,
            "invalid Field Survey firmware source")
    for key in ("app_elf_sha256", "factory_sha256", "firmware_sha256",
                "map_sha256"):
        require_hash(candidate.get(key), f"candidate.{key}")

    journey = value.get("journey", {})
    require(journey.get("status") == "pass" and
            journey.get("gate_eligible") is True,
            "full Field Survey journey did not pass")
    require(journey.get("boot_generation") == 8 and
            journey.get("post_commit_generation") == 10 and
            journey.get("post_commit_observations") == 51 and
            journey.get("post_commit_physical_writes") == 0,
            "cold read-only recovery invariant changed")
    require(journey.get("cleanup_complete") is True and
            journey.get("final_page") == "home" and
            journey.get("final_runtime_owner") == "none" and
            journey.get("final_lease_mask") == 0 and
            journey.get("final_hil_session_active") is False,
            "Field Survey journey did not finish cleanly")
    require_hash(journey.get("run_sha256"), "journey.run_sha256")
    require_hash(journey.get("artifact_index_sha256"),
                 "journey.artifact_index_sha256")

    first = journey.get("first_visit", {})
    revisit = journey.get("revisit", {})
    require(first == {
        "ble_begin_error": 0,
        "ble_begin_heap_largest_before": 31732,
        "ble_devices": 36,
        "complete": True,
        "generation": 9,
        "new": 55,
        "observations": 55,
        "pipeline_drops": 0,
        "seen_again": 0,
        "source_passes": {"ble": 1, "wifi": 1},
        "wifi_access_points": 14,
        "wifi_stations": 5,
    }, "first-visit facts changed")
    require(revisit == {
        "baseline_unique": 55,
        "ble_begin_error": 0,
        "ble_begin_heap_largest_before": 31732,
        "ble_devices": 31,
        "complete": True,
        "generation": 10,
        "missing": 15,
        "new": 11,
        "observations": 51,
        "pipeline_drops": 0,
        "seen_again": 40,
        "source_passes": {"ble": 1, "wifi": 1},
        "wifi_access_points": 15,
        "wifi_stations": 5,
    }, "revisit facts changed")

    export = value.get("export_verification", {})
    require(export.get("accepted_by_composed_machine_check") is True and
            export.get("device_actions_complete") is True,
            "export semantics were not machine accepted")
    require(export.get("raw_runner_status") == "failed" and
            export.get("raw_runner_failure") ==
            "export.library.library_entries: 2 != 1",
            "stale export oracle failure is not retained honestly")
    require(export.get("library_entries") == 2 and
            export.get("library_selected_kind") == "session" and
            export.get("library_generation") == 10 and
            export.get("library_persistent") is True,
            "Field Survey Library selection is not exact")
    require(export.get("corrected_oracle_tests") == 15 and
            isinstance(export.get("corrected_oracle_commit"), str) and
            HEX40.fullmatch(export["corrected_oracle_commit"]) is not None,
            "corrected export oracle is not pinned")
    for key in ("corrected_oracle_runner_sha256", "export_run_sha256",
                "export_artifact_index_sha256", "runner_before_fix_sha256"):
        require_hash(export.get(key), f"export.{key}")
    require(export.get("writes_committed") == 0 and
            export.get("radio_touched") is False,
            "read-only export touched radio or storage")
    require(export.get("native") == {
        "ble_devices": 31,
        "bytes": 4661,
        "records": 51,
        "sha256": "3c1de02bdf558f80e1615e14526809eb642ed388549fd57817de27c92af2557b",
        "status": "complete",
        "wifi_access_points": 15,
        "wifi_stations": 5,
    }, "native export facts changed")
    require(export.get("wigle") == {
        "bytes": 3164,
        "readiness": "untimed_unlocated",
        "records": 46,
        "sha256": "a6d12d7769a8809d02285e65dc6e74b5ce659f687de490b1b8ce7bd947b92805",
        "skipped_wifi_stations": 5,
        "status": "complete",
        "upload_ready": False,
    }, "WiGLE export facts changed")

    precursors = value.get("precursors", {})
    memory = precursors.get("dev365_memory_failure", {})
    require(memory.get("accepted") is False and
            memory.get("ble_begin_error") == 257 and
            memory.get("ble_begin_heap_largest_before") == 26612 and
            memory.get("cleanup_complete") is True,
            "dev.365 fail-closed memory precursor changed")
    transport = precursors.get("post_export_transport", {})
    require(transport.get("accepted") is False and
            transport.get("status") == "infrastructure_only" and
            transport.get("device_actions_started") is False and
            len(transport.get("run_sha256", [])) == 2,
            "post-export transport precursors changed")
    require_hash(memory.get("run_sha256"), "precursor.memory.run")
    for index, digest in enumerate(transport.get("run_sha256", [])):
        require_hash(digest, f"precursor.transport.run[{index}]")

    resources = value.get("resources", {})
    require(resources == {
        "free_ota_bytes": 546672,
        "linked_flash_bytes": 3647128,
        "required_free_ota_bytes": 524288,
        "static_ram_bytes": 234976,
    }, "Field Survey resource bound changed")
    require(value.get("visual_plain_language_review_passed") is True,
            "Field Survey screen review is not accepted")
    screens = value.get("screens", {})
    require(len(screens) == 10, "all five PNG/RGB565 screen pairs are not bound")
    for key, digest in screens.items():
        require_hash(digest, f"screens.{key}")

    require(value.get("privacy") == {
        "ambient_bssid_retained": False,
        "ambient_raw_csv_retained": False,
        "ambient_ssid_retained": False,
        "ambient_vendor_retained": False,
        "raw_run_retained": False,
        "screen_hashes_only": True,
    }, "privacy-minimal retention contract changed")
    forbidden = {"ssid", "bssid", "vendor", "mac", "identity"}
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
    print("field_survey_journey_hil_acceptance: PASS")


if __name__ == "__main__":
    main()
