#!/usr/bin/env python3
"""Fail closed on the retained CAP-050 passive Wi-Fi station slice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / (
    "tests/hil/evidence/"
    "board-01-field-survey-stations-1.0.0-dev.266.json"
)


def failures(record: dict[str, Any]) -> list[str]:
    result: list[str] = []

    def exact(path: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            result.append(f"{path}: {actual!r} != {expected!r}")

    exact("schema", record.get("schema"),
          "leshy.field_survey_stations.acceptance.v1")
    exact("status", record.get("status"),
          "pass_station_slice_not_capability_complete")
    exact("board", record.get("board"), "board-01")
    exact("cid", record.get("cid"),
          "FE343253440000002000000055019CB7")
    exact("evidence_ids", record.get("evidence_ids"),
          ["E-BUILD-187", "E-AUTO-162", "E-HIL-201", "RB-M198"])

    scope = record.get("scope", {})
    for field in (
            "receive_only", "live_station_capture_accepted",
            "native_station_export_accepted",
            "wigle_station_exclusion_accepted"):
        exact(f"scope.{field}", scope.get(field), True)
    exact("scope.cap_050_complete", scope.get("cap_050_complete"), False)
    exact("scope.trusted_location_time_accepted",
          scope.get("trusted_location_time_accepted"), False)

    candidate = record.get("candidate", {})
    for field, expected in (
            ("version", "1.0.0-dev.266"),
            ("source_commit", "ffd8f8f23cd3153a5de415049fc2665544af66c1"),
            ("firmware_bytes", 3458560),
            ("firmware_sha256", "c3638e1c0266eacf88cef69e275152bf6589e5f5cfcecb941501b82709026447"),
            ("factory_bytes", 3524096),
            ("factory_sha256", "cf2f69d5482bd5da5c966af8518156a96548462b6bf44d3b56d33791718bc27e"),
            ("app_elf_sha256", "1066d57bcc0cb4fd4dce311a6db6e72a87be83e1513c93be26f2c434da4112aa"),
            ("map_sha256", "376a659a1da05132e50e4fd8671e5e50c42c719ca49ff6ec3cb25887cf1730ab"),
            ("static_ram_bytes", 231624),
            ("linked_flash_bytes", 3458056),
            ("ota_slot_free_bytes", 735744)):
        exact(f"candidate.{field}", candidate.get(field), expected)

    automation = record.get("automation", {})
    for field, expected in (
            ("runner_sha256", "a61e5a9766e9db84fa8350c0f7e9a15542422d8a172ca79648f0af4920894498"),
            ("runner_tests_sha256", "3de0715dbe5b2025a49571526914adeaaaa6765017ff7cb50f15282c20b59a4e"),
            ("product_contract_sha256", "90ec5d14945c5a1838d2120d13d3d703ad2134b74f219c402a7dc80ef7e33397"),
            ("mode", "full_then_export_delta"),
            ("accepted_candidate_fresh_flashes", 1),
            ("development_candidate_flashes", 3),
            ("export_reused_exact_flash", True),
            ("export_radio_scans", 0), ("export_storage_commits", 0),
            ("raw_csv_written_to_host", False)):
        exact(f"automation.{field}", automation.get(field), expected)

    corrections = record.get("development_corrections", [])
    exact("development_corrections.count", len(corrections), 2)
    if len(corrections) == 2:
        exact("development_corrections.versions",
              [item.get("version") for item in corrections],
              ["1.0.0-dev.264", "1.0.0-dev.265"])
        for index, correction in enumerate(corrections):
            exact(f"development_corrections.{index}.cleanup_complete",
                  correction.get("cleanup_complete"), True)
            exact(f"development_corrections.{index}.final_page",
                  correction.get("final_page"), "home")
            exact(f"development_corrections.{index}.final_owner",
                  correction.get("final_owner"), "none")
            exact(f"development_corrections.{index}.final_lease_mask",
                  correction.get("final_lease_mask"), 0)

    physical = record.get("physical", {})
    for field, expected in (
            ("visit_run_id", "4efa53e1e5da84afbb8a253effe38dca"),
            ("visit_run_sha256", "5ab03756d729891444d87cb28e55e31b6663e28089abedbe29d99d519706385d"),
            ("visit_artifact_manifest_sha256", "d8cf822f0db723f6f1bcfe258cea0d5c40ac138304b11f86c6ee2f2d6cf6cc7d"),
            ("fresh_flash", True),
            ("export_run_id", "eee900ad0bc32079476125d2b4119082"),
            ("export_run_sha256", "707845f9b8488cf7e346a0b3367d7a81671197f42abf0cd1791525a03314a989"),
            ("export_artifact_manifest_sha256", "a3937b645bb7d63f8bcb9ce142eef08cfb092004496a5e8c443380854ca26141"),
            ("final_page", "home"), ("final_owner", "none"),
            ("final_lease_mask", 0), ("hil_active_after", False)):
        exact(f"physical.{field}", physical.get(field), expected)

    for name, expected in (
            ("first_visit", (174, 51, 16, 2, 33, 47, 114)),
            ("revisit", (175, 51, 15, 2, 34, 44, 109))):
        visit = physical.get(name, {})
        fields = ("generation", "observations", "wifi_access_points",
                  "wifi_stations", "ble_devices", "channel_hops",
                  "frames_reported")
        for field, value in zip(fields, expected):
            exact(f"{name}.{field}", visit.get(field), value)
        exact(f"{name}.radio_total",
              visit.get("wifi_access_points", 0) +
              visit.get("wifi_stations", 0) + visit.get("ble_devices", 0),
              visit.get("observations"))
        for field in ("survey_drops", "wifi_drops", "station_drops",
                      "ble_drops"):
            exact(f"{name}.{field}", visit.get(field), 0)
        exact(f"{name}.cleanup_complete", visit.get("cleanup_complete"), True)
    revisit = physical.get("revisit", {})
    exact("revisit.compare", (revisit.get("seen_again"),
                               revisit.get("new_this_visit"),
                               revisit.get("missing_this_visit")),
          (43, 8, 8))

    recovery = physical.get("cold_recovery", {})
    for field, expected in (
            ("generation", 175), ("observations", 51),
            ("status", "admitted"), ("attempts", 1),
            ("transient_retries", 0), ("timeout_restarts", 0),
            ("mounted_read_only", True), ("read_only_guaranteed", True),
            ("write_enabled", False), ("physical_write_calls", 0),
            ("blocked_write_attempts", 0), ("cleanup_complete", True),
            ("owned_after", 0)):
        exact(f"cold_recovery.{field}", recovery.get(field), expected)

    native = physical.get("native", {})
    for field, expected in (
            ("records", 51), ("observations", 51), ("bytes", 4593),
            ("payload_sha256", "559085c2ceef04e7ae1327625ee428f919c95b43d6f82414d9bc924c57d5cc25"),
            ("wifi_access_points", 15), ("wifi_stations", 2),
            ("ble_devices", 34), ("deduplicated", True)):
        exact(f"native.{field}", native.get(field), expected)
    exact("native.radio_total", native.get("wifi_access_points", 0) +
          native.get("wifi_stations", 0) + native.get("ble_devices", 0),
          native.get("records"))

    wigle = physical.get("wigle", {})
    for field, expected in (
            ("format", "wigle_wifi_1.6"), ("records", 49),
            ("bytes", 3362),
            ("payload_sha256", "8a4a44bcd21e610b649d661eb0aefea6490b474ca9fecaa7cd2e407b48658f5c"),
            ("wifi_access_points", 15), ("wifi_stations_skipped", 2),
            ("ble_devices", 34), ("readiness", "untimed_unlocated"),
            ("trusted_utc", False), ("trusted_location", False),
            ("upload_ready", False)):
        exact(f"wigle.{field}", wigle.get(field), expected)
    exact("wigle.radio_total", wigle.get("wifi_access_points", 0) +
          wigle.get("ble_devices", 0), wigle.get("records"))
    exact("export.station_boundary",
          native.get("records", 0) - wigle.get("records", 0),
          wigle.get("wifi_stations_skipped"))

    privacy = record.get("privacy", {})
    for field in ("ambient_identifiers_retained", "raw_radio_payloads_retained",
                  "raw_export_payloads_retained"):
        exact(f"privacy.{field}", privacy.get(field), False)
    exact("open_gates", record.get("open_gates"), [
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
        "Field Survey station acceptance passed: exact generations 174/175 "
        "each contain two live stations with zero drops; native preserves two "
        "station rows, WiGLE skips exactly two, and cleanup is Home/none/lease 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
