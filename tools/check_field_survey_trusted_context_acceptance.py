#!/usr/bin/env python3
"""Fail closed on the retained CAP-050 trusted-context software slice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / (
    "tests/hil/evidence/"
    "board-01-field-survey-trusted-context-1.0.0-dev.267.json"
)


def failures(record: dict[str, Any]) -> list[str]:
    result: list[str] = []

    def exact(path: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            result.append(f"{path}: {actual!r} != {expected!r}")

    exact("schema", record.get("schema"),
          "leshy.field_survey_trusted_context.acceptance.v1")
    exact("status", record.get("status"),
          "pass_trusted_context_software_slice_not_capability_complete")
    exact("board", record.get("board"), "board-01")
    exact("cid", record.get("cid"),
          "FE343253440000002000000055019CB7")
    exact("evidence_ids", record.get("evidence_ids"),
          ["E-BUILD-188", "E-AUTO-163", "E-HIL-202", "RB-M199"])

    scope = record.get("scope", {})
    for field in (
            "receive_only", "trusted_context_persistence_accepted",
            "located_timed_export_formatter_accepted",
            "stock_absence_path_physically_accepted"):
        exact(f"scope.{field}", scope.get(field), True)
    exact("scope.cap_050_complete", scope.get("cap_050_complete"), False)
    exact("scope.gps_hardware_profile_physically_accepted",
          scope.get("gps_hardware_profile_physically_accepted"), False)

    candidate = record.get("candidate", {})
    for field, expected in (
            ("version", "1.0.0-dev.267"),
            ("source_commit", "eb23d614785420a10588a4ae5a8d3e351021702b"),
            ("firmware_bytes", 3460272),
            ("firmware_sha256", "8d6982923dafdca1d7522e197eb7119cf69cbcb7045087bb193a58d2313cca55"),
            ("factory_bytes", 3525808),
            ("factory_sha256", "b3ba37cb6201e73682dc4f1aed5ed3cd999567382cc4f76e8e44b967de7ad63c"),
            ("app_elf_sha256", "c33fed0f41e7a5594342aa3f3bc58787048793460bf39b7de2cd0d6d1945f3a1"),
            ("map_sha256", "5f6f24f36d1ea80bf7d1b2545b45addfe62cc52bd418c7ec19c42b1f6d1c7a46"),
            ("static_ram_bytes", 231736),
            ("linked_flash_bytes", 3459768),
            ("ota_slot_free_bytes", 734032)):
        exact(f"candidate.{field}", candidate.get(field), expected)

    software = record.get("software", {})
    for field, expected in (
            ("session_schema", 9),
            ("legacy_schemas_readable", list(range(1, 9))),
            ("trusted_record_bytes", 64),
            ("trusted_record_magic", "LTGC"),
            ("trusted_record_wire_version", 1),
            ("accepted_source", "gps_nmea"),
            ("maximum_fix_age_ms", 10000),
            ("immutable_after_first_observation", True),
            ("strict_calendar_utc_validation", True),
            ("strict_coordinate_validation", True),
            ("upload_ready_requires_utc_and_location", True),
            ("clean_target_tests_sha256", "f334934c697109af64a9c5018feaf8aeb118000c00bd4c2b486fe69e3e4836ce"),
            ("session_codec_sha256", "a637df4d84bd7ebd23056292ba6051df8e5c7b75ee6ad6eab36581134f3779e0"),
            ("survey_session_sha256", "ecf48a58236d5b4eadf7c57df728921b6eb9169462c074c076f8d62101162d40")):
        exact(f"software.{field}", software.get(field), expected)

    automation = record.get("automation", {})
    for field, expected in (
            ("runner_sha256", "a61e5a9766e9db84fa8350c0f7e9a15542422d8a172ca79648f0af4920894498"),
            ("runner_tests_sha256", "3de0715dbe5b2025a49571526914adeaaaa6765017ff7cb50f15282c20b59a4e"),
            ("product_contract_sha256", "023108c3e0ad6661d0562fa4a718fa6a559e8ab3931668886d8cf7a88157c92d"),
            ("mode", "focused_export_delta"),
            ("accepted_candidate_fresh_flashes", 1),
            ("radio_scans", 0), ("storage_commits", 0),
            ("mac_wifi_touched", False), ("clone_touched", False),
            ("cardputer_touched", False),
            ("raw_csv_written_to_host", False)):
        exact(f"automation.{field}", automation.get(field), expected)

    correction = record.get("infrastructure_correction", {})
    for field, expected in (
            ("failed_run_sha256", "8d7cdf6a65245c0808b418d1383cde48e561d746e7ec3700bf002b943e9b1c7e"),
            ("candidate_was_flashed", False),
            ("candidate_failure", False)):
        exact(f"infrastructure_correction.{field}", correction.get(field),
              expected)

    physical = record.get("physical", {})
    for field, expected in (
            ("run_id", "b5624a5a2de5da0ff4c7817ce2cb872f"),
            ("run_sha256", "70969179d1af4e379086540ecf78febd240ea3c1ebe4471999193e8cfa685604"),
            ("artifact_manifest_sha256", "bf05f8e57298758d40362b412a780dcef1d334d2efdd91d5e58a7099965c8f1c"),
            ("fresh_flash", True), ("gate_eligible", True),
            ("generation", 175), ("observations", 51),
            ("recovery_attempts", 2),
            ("recovery_transient_retries", 1),
            ("recovery_timeout_restarts", 0),
            ("mounted_read_only", True), ("read_only_guaranteed", True),
            ("write_enabled", False), ("physical_write_calls", 0),
            ("blocked_write_attempts", 0),
            ("hil_session_begin_end_match", True),
            ("cleanup_complete", True), ("final_page", "home"),
            ("final_owner", "none"), ("final_lease_mask", 0),
            ("safety_state", "armed"), ("hil_active_after", False)):
        exact(f"physical.{field}", physical.get(field), expected)

    native = physical.get("native", {})
    for field, expected in (
            ("records", 51), ("bytes", 4593),
            ("payload_sha256", "559085c2ceef04e7ae1327625ee428f919c95b43d6f82414d9bc924c57d5cc25"),
            ("wifi_access_points", 15), ("wifi_stations", 2),
            ("ble_devices", 34)):
        exact(f"native.{field}", native.get(field), expected)
    exact("native.radio_total", native.get("wifi_access_points", 0) +
          native.get("wifi_stations", 0) + native.get("ble_devices", 0),
          native.get("records"))

    wigle = physical.get("wigle", {})
    for field, expected in (
            ("format", "wigle_wifi_1.6"), ("records", 49),
            ("bytes", 3362),
            ("payload_sha256", "c48bbd20188dda161fa0470a03894c281918eb2669c53b38bb3d4f279bcb8d6b"),
            ("wifi_access_points", 15), ("wifi_stations_skipped", 2),
            ("ble_devices", 34), ("readiness", "untimed_unlocated"),
            ("trusted_source", "none"), ("trusted_utc", False),
            ("trusted_location", False), ("fix_age_ms", 0),
            ("upload_ready", False)):
        exact(f"wigle.{field}", wigle.get(field), expected)
    exact("wigle.radio_total", wigle.get("wifi_access_points", 0) +
          wigle.get("ble_devices", 0), wigle.get("records"))

    privacy = record.get("privacy", {})
    for field in ("ambient_identifiers_retained", "raw_radio_payloads_retained",
                  "raw_export_payloads_retained"):
        exact(f"privacy.{field}", privacy.get(field), False)
    deferred = record.get("deferred_physical_gate", {})
    exact("deferred.required_fixture", deferred.get("required_fixture"),
          "a separately owned GPS board profile with non-conflicting pins")
    exact("open_gates", record.get("open_gates"), [
        "physically qualify an optional trusted GPS board profile when the fixture exists",
    ])
    return result


def main() -> int:
    record = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    problems = failures(record)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1
    print(
        "Field Survey trusted-context acceptance passed: schema v9 persists "
        "strict optional GPS/UTC, stock hardware remains truthfully "
        "untimed/unlocated, and physical GPS qualification is explicitly deferred"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
