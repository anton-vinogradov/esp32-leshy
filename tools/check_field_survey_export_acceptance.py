#!/usr/bin/env python3
"""Fail closed on the retained CAP-050 native/WiGLE export slice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / (
    "tests/hil/evidence/"
    "board-01-field-survey-export-1.0.0-dev.263.json"
)


def failures(record: dict[str, Any]) -> list[str]:
    result: list[str] = []

    def exact(path: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            result.append(f"{path}: {actual!r} != {expected!r}")

    exact("schema", record.get("schema"),
          "leshy.field_survey_export.acceptance.v1")
    exact("status", record.get("status"),
          "pass_export_slice_not_capability_complete")
    exact("board", record.get("board"), "board-01")
    exact("cid", record.get("cid"),
          "FE343253440000002000000055019CB7")
    exact("evidence_ids", record.get("evidence_ids"),
          ["E-BUILD-186", "E-AUTO-161", "E-HIL-200", "RB-M197"])

    scope = record.get("scope", {})
    for field in (
            "receive_only", "result_to_library_route_source_accepted",
            "native_export_accepted", "wigle_export_accepted"):
        exact(f"scope.{field}", scope.get(field), True)
    exact("scope.cap_050_complete", scope.get("cap_050_complete"), False)
    exact("scope.live_station_capture_accepted",
          scope.get("live_station_capture_accepted"), False)
    exact("scope.trusted_location_time_accepted",
          scope.get("trusted_location_time_accepted"), False)

    candidate = record.get("candidate", {})
    for field, expected in (
            ("version", "1.0.0-dev.263"),
            ("source_commit", "0f46b4db840bf38e3beac6424623c33fca8e749e"),
            ("firmware_bytes", 3455888),
            ("firmware_sha256", "be9a5061a59db614e804e36bf1f08b325dff31da93075c92a1eace4b2f3a8d35"),
            ("factory_bytes", 3521424),
            ("factory_sha256", "82d4a023769178714aeaecd243a05a01e101bdbce5d40cb21e7fe3c7e05c13d5"),
            ("app_elf_sha256", "9906543f7f541778f7ba5969a7b74e2de81f83b66a30ff1caebc0f509fd0571f"),
            ("map_sha256", "47edfc75a3d18222b6ea68e4c2f0b59b3d5b21a1d47ba2fab5b20d9f6645239b"),
            ("static_ram_bytes", 231624),
            ("linked_flash_bytes", 3455384),
            ("ota_slot_free_bytes", 738416)):
        exact(f"candidate.{field}", candidate.get(field), expected)

    automation = record.get("automation", {})
    for field, expected in (
            ("runner_source_commit", "648a17a33236390558fdaf47712b23ccdf838130"),
            ("runner_sha256", "365c36224ee4ec02a5daa923d59cb8df059b89c46da538e9b6f1f6f661a1053b"),
            ("runner_tests_sha256", "9541c1796f28403a0dca1d6278074ee25647d2851fa587f7aa3da20035904356"),
            ("product_contract_sha256", "90ec5d14945c5a1838d2120d13d3d703ad2134b74f219c402a7dc80ef7e33397"),
            ("mode", "export"), ("fresh_flashes", 1),
            ("accepted_run_reused_exact_flash", True),
            ("radio_scans", 0), ("storage_commits", 0),
            ("raw_csv_written_to_host", False)):
        exact(f"automation.{field}", automation.get(field), expected)

    correction = record.get("oracle_correction", {})
    exact("oracle.failed_run_sha256",
          correction.get("failed_run_sha256"),
          "141ab8f16bd7caa3e2958c355a011c6b6362062aef400349ab3c1aefa3cbc4fc")
    exact("oracle.firmware_and_exports_were_valid",
          correction.get("firmware_and_exports_were_valid"), True)
    exact("oracle.failed_run_cleanup_complete",
          correction.get("failed_run_cleanup_complete"), True)
    exact("oracle.failed_run_final_lease_mask",
          correction.get("failed_run_final_lease_mask"), 0)
    exact("oracle.accepted_after_oracle_only_fix",
          correction.get("accepted_after_oracle_only_fix"), True)
    if len(correction.get("only_failures", [])) != 2:
        result.append("oracle.only_failures: expected two exact oracle defects")

    physical = record.get("physical", {})
    for field, expected in (
            ("run_id", "25dd1614d78051ed5482207bfb1e6339"),
            ("run_sha256", "93d6e7facc8fd715133d6ce5fbf2d4446cdf804658b6b51b27fae47044684fe2"),
            ("artifact_manifest_sha256", "f7edbaabf371ba947c6983ed4bc644f2279cf20df0ec25b4edeab9676de68ee3"),
            ("generation", 172), ("observations", 52),
            ("recovery_status", "admitted"), ("recovery_attempts", 1),
            ("recovery_transient_retries", 0),
            ("recovery_timeout_restarts", 0),
            ("mounted_read_only", True), ("read_only_guaranteed", True),
            ("write_enabled", False), ("physical_write_calls", 0),
            ("blocked_write_attempts", 0),
            ("recovery_cleanup_complete", True),
            ("recovery_owned_after", 0),
            ("export_ready_png_sha256", "0c31c83a19c11bb58444080a290a085e3ad8a43e171e22c94a92c70b77608b88"),
            ("export_ready_rgb565_sha256", "7905f0ad463e5df74e2945c43726301859db8f5206fe24727e84c3d73a1ad30f"),
            ("final_page", "home"), ("final_owner", "none"),
            ("final_lease_mask", 0), ("hil_active_after", False)):
        exact(f"physical.{field}", physical.get(field), expected)

    native = physical.get("native", {})
    for field, expected in (
            ("records", 52), ("observations", 52), ("bytes", 4650),
            ("payload_sha256", "9e73afcdb6b496ec865d5fbca6cffe121beaa8bfc424446e7b90ab5843fe7844"),
            ("wifi_access_points", 16), ("wifi_stations", 0),
            ("ble_devices", 36), ("deduplicated", True)):
        exact(f"native.{field}", native.get(field), expected)
    exact("native.radio_total",
          native.get("wifi_access_points", 0) +
          native.get("wifi_stations", 0) + native.get("ble_devices", 0),
          native.get("records"))

    wigle = physical.get("wigle", {})
    for field, expected in (
            ("format", "wigle_wifi_1.6"), ("records", 52),
            ("bytes", 3573),
            ("payload_sha256", "0823225da8733b7f63bdf2e412b1553060ed6a8d1cf486094be3a3575ca34195"),
            ("wifi_access_points", 16), ("ble_devices", 36),
            ("readiness", "untimed_unlocated"), ("trusted_utc", False),
            ("trusted_location", False), ("upload_ready", False)):
        exact(f"wigle.{field}", wigle.get(field), expected)
    exact("wigle.radio_total",
          wigle.get("wifi_access_points", 0) + wigle.get("ble_devices", 0),
          wigle.get("records"))

    privacy = record.get("privacy", {})
    for field in (
            "ambient_identifiers_retained", "raw_radio_payloads_retained",
            "raw_export_payloads_retained"):
        exact(f"privacy.{field}", privacy.get(field), False)
    exact("open_gates", record.get("open_gates"), [
        "capture passive Wi-Fi station observations",
        "admit optional trusted GPS and UTC",
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
        "Field Survey export acceptance passed: exact generation 172/52, "
        "52 native and truthful local WiGLE rows, zero scans/writes, and "
        "final Home/none/lease 0; station capture and trusted GPS/UTC remain open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
