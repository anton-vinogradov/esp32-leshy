#!/usr/bin/env python3
"""Fail closed on the retained CAP-050 first/revisit/cold lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / (
    "tests/hil/evidence/"
    "board-01-field-survey-visits-1.0.0-dev.262.json"
)


def failures(record: dict[str, Any]) -> list[str]:
    result: list[str] = []

    def exact(path: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            result.append(f"{path}: {actual!r} != {expected!r}")

    exact("schema", record.get("schema"),
          "leshy.field_survey_visits.acceptance.v1")
    exact("status", record.get("status"),
          "pass_visit_lifecycle_not_capability_complete")
    exact("board", record.get("board"), "board-01")
    exact("cid", record.get("cid"),
          "FE343253440000002000000055019CB7")
    exact("evidence_ids", record.get("evidence_ids"),
          ["E-BUILD-185", "E-AUTO-160", "E-HIL-199", "RB-M196"])

    scope = record.get("scope", {})
    for field in (
            "receive_only", "field_visit_lifecycle_accepted",
            "one_pass_auto_pause", "first_visit_committed",
            "revisit_committed", "deterministic_incomplete_negative",
            "post_commit_cold_recovery"):
        exact(f"scope.{field}", scope.get(field), True)
    exact("scope.cap_050_complete", scope.get("cap_050_complete"), False)
    for field in (
            "native_export_accepted", "wigle_export_accepted",
            "live_station_capture_accepted", "trusted_location_time_accepted"):
        exact(f"scope.{field}", scope.get(field), False)

    candidate = record.get("candidate", {})
    exact("candidate.version", candidate.get("version"), "1.0.0-dev.262")
    exact("candidate.source_commit", candidate.get("source_commit"),
          "99aacd01336a065e18b52035ec243e2eb47abd92")
    exact("candidate.firmware_bytes", candidate.get("firmware_bytes"), 3447824)
    exact("candidate.firmware_sha256", candidate.get("firmware_sha256"),
          "8e21225c6041126a7ff11b0fe50b64d2dd3e64705e9b592cc33d3820aa551ae1")
    exact("candidate.factory_bytes", candidate.get("factory_bytes"), 3513360)
    exact("candidate.factory_sha256", candidate.get("factory_sha256"),
          "a60df4249a7005c9671dab14eeeea160cee553de199aa2055d16da1b4c0994ec")
    exact("candidate.app_elf_sha256", candidate.get("app_elf_sha256"),
          "deeccd42afe1112da6b47c29eb5269ce6b9da332819aef2d0bd735b6321b91a6")
    exact("candidate.map_sha256", candidate.get("map_sha256"),
          "3aaeb56afed302d81003bf8e5494346db65b21b970e2c6a2261e4ac4140f77a2")
    exact("candidate.static_ram_bytes", candidate.get("static_ram_bytes"),
          231624)
    exact("candidate.ota_slot_free_bytes",
          candidate.get("ota_slot_free_bytes"), 746480)

    automation = record.get("automation", {})
    exact("automation.runner_sha256", automation.get("runner_sha256"),
          "bde73e66c9f3423905a269e567d28e684f5655df65acdb2154ea61b3c1788072")
    exact("automation.full_run_reported_gate_eligible_before_cold_fix",
          automation.get("full_run_reported_gate_eligible_before_cold_fix"),
          True)
    exact("automation.full_run_contains_post_commit_cold_recovery",
          automation.get("full_run_contains_post_commit_cold_recovery"), False)
    exact("automation.accepted_only_with_separate_recovery_delta",
          automation.get("accepted_only_with_separate_recovery_delta"), True)
    exact("automation.corrected_runner_requires_post_commit_recovery_for_future_full_gate",
          automation.get(
              "corrected_runner_requires_post_commit_recovery_for_future_full_gate"),
          True)
    exact("automation.recovery_delta_scanned_or_wrote",
          automation.get("recovery_delta_scanned_or_wrote"), False)

    preflight = record.get("preflight", {})
    exact("preflight.run_id", preflight.get("run_id"),
          "b92c663b9200012ffd100c7c4fdd9752")
    exact("preflight.run_sha256", preflight.get("run_sha256"),
          "5f51b900f1da5a61d1eada06e8cdcc0d23787b3621592a9002a6406eacdbe91a")
    exact("preflight.artifact_manifest_sha256",
          preflight.get("artifact_manifest_sha256"),
          "f0b270227c1b3ab053749081292d74b0ade8945a78efeaeed084f5bd4b911f09")
    for field in ("scan_cycles", "wifi_scan_cycles", "ble_scan_cycles"):
        exact(f"preflight.{field}", preflight.get(field), 1)
    exact("preflight.pipeline_received", preflight.get("pipeline_received"),
          preflight.get("wifi_accepted", 0) + preflight.get("ble_accepted", 0))
    exact("preflight.pipeline_forwarded", preflight.get("pipeline_forwarded"),
          preflight.get("pipeline_received"))
    exact("preflight.pipeline_dropped", preflight.get("pipeline_dropped"), 0)
    exact("preflight.generation_after", preflight.get("generation_after"),
          preflight.get("generation_before"))
    exact("preflight.writes_committed", preflight.get("writes_committed"), 0)
    exact("preflight.auto_paused", preflight.get("auto_paused"), True)
    exact("preflight.cleanup_complete", preflight.get("cleanup_complete"), True)

    visit_run = record.get("visit_run", {})
    exact("visit_run.run_id", visit_run.get("run_id"),
          "d2d8d68fe8e2b10229245868ffbff76d")
    exact("visit_run.run_sha256", visit_run.get("run_sha256"),
          "0ce175ae9e5d161c334abd2513080de29bb172d8306a547a179b430157d3fa51")
    exact("visit_run.artifact_manifest_sha256",
          visit_run.get("artifact_manifest_sha256"),
          "910d0002f185ac6cf5f2730449cae48d781cbc9bed26be8c07086cce67e88e6f")
    exact("visit_run.reused_exact_flash", visit_run.get("reused_exact_flash"),
          True)
    for name in ("first_visit", "revisit"):
        visit = visit_run.get(name, {})
        for field in ("scan_cycles", "wifi_scan_cycles", "ble_scan_cycles"):
            exact(f"visit_run.{name}.{field}", visit.get(field), 1)
        exact(f"visit_run.{name}.selected_source_mask",
              visit.get("selected_source_mask"), 3)
        exact(f"visit_run.{name}.active_source_mask",
              visit.get("active_source_mask"), 3)
        exact(f"visit_run.{name}.unavailable_source_mask",
              visit.get("unavailable_source_mask"), 0)
        accepted = visit.get("wifi_accepted", 0) + visit.get("ble_accepted", 0)
        exact(f"visit_run.{name}.pipeline_received",
              visit.get("pipeline_received"), accepted)
        exact(f"visit_run.{name}.pipeline_forwarded",
              visit.get("pipeline_forwarded"), accepted)
        exact(f"visit_run.{name}.pipeline_dropped",
              visit.get("pipeline_dropped"), 0)
        exact(f"visit_run.{name}.current_unique",
              visit.get("current_unique"), accepted)
        exact(f"visit_run.{name}.radio_counts",
              visit.get("wifi_access_points", 0) +
              visit.get("wifi_stations", 0) + visit.get("ble_devices", 0),
              visit.get("current_unique"))
        if visit.get("store_bytes_written", 0) < 1:
            result.append(f"visit_run.{name}.store_bytes_written: expected > 0")
        exact(f"visit_run.{name}.timeline_windows_persisted",
              visit.get("timeline_windows_persisted"), 6)
        exact(f"visit_run.{name}.cleanup_complete",
              visit.get("cleanup_complete"), True)

    first = visit_run.get("first_visit", {})
    revisit = visit_run.get("revisit", {})
    for path, actual, expected in (
            ("first.generation_before", first.get("generation_before"), 170),
            ("first.generation_after", first.get("generation_after"), 171),
            ("first.current_unique", first.get("current_unique"), 46),
            ("revisit.generation_before", revisit.get("generation_before"), 171),
            ("revisit.generation_after", revisit.get("generation_after"), 172),
            ("revisit.current_unique", revisit.get("current_unique"), 52),
            ("revisit.baseline_unique", revisit.get("baseline_unique"), 46),
            ("revisit.seen_again", revisit.get("seen_again"), 42),
            ("revisit.new_this_visit", revisit.get("new_this_visit"), 10),
            ("revisit.missing_this_visit", revisit.get("missing_this_visit"), 4)):
        exact(path, actual, expected)
    for path, actual, expected in (
            ("first.setup_png_sha256", first.get("setup_png_sha256"),
             "2803b7aa46f58e1ddafcca249da2700c118cf7e5d4af146a24bbbf5ad3b8c08b"),
            ("first.result_png_sha256", first.get("result_png_sha256"),
             "9b4d55348294b00e77c1b21c722440c8d5b3289e71d45271063f2078fe2b8a6f"),
            ("revisit.setup_png_sha256", revisit.get("setup_png_sha256"),
             "85d3082ae0c9fc18ff6611c26c5599ff07e7010ea3d09e00283bb31059104b39"),
            ("revisit.result_png_sha256", revisit.get("result_png_sha256"),
             "a9a8f534c5443a781c0c979a0654b0e57d0e36d0dd3ad29d7086ebc7a2c6ac9f")):
        exact(path, actual, expected)
    exact("first generation", first.get("generation_after"),
          first.get("generation_before", -1) + 1)
    exact("revisit generation before", revisit.get("generation_before"),
          first.get("generation_after"))
    exact("revisit generation", revisit.get("generation_after"),
          revisit.get("generation_before", -1) + 1)
    exact("first set arithmetic", first.get("new_this_visit"),
          first.get("current_unique"))
    exact("revisit current set arithmetic",
          revisit.get("seen_again", 0) + revisit.get("new_this_visit", 0),
          revisit.get("current_unique"))
    exact("revisit baseline set arithmetic",
          revisit.get("seen_again", 0) + revisit.get("missing_this_visit", 0),
          revisit.get("baseline_unique"))
    exact("revisit baseline identity", revisit.get("baseline_unique"),
          first.get("current_unique"))

    negative = visit_run.get("incomplete_negative", {})
    exact("incomplete_negative.status", negative.get("status"), "incomplete")
    exact("incomplete_negative.build_status",
          negative.get("build_status"), "session_not_stopped")
    for field in ("complete", "session_stopped", "radio_touched",
                  "storage_touched"):
        exact(f"incomplete_negative.{field}", negative.get(field), False)
    exact("incomplete_negative.session_id_exact",
          negative.get("session_id_exact"), True)

    cold = record.get("cold_recovery", {})
    exact("cold_recovery.run_id", cold.get("run_id"),
          "035b25d58d379ca4991ae5cc2f12860f")
    exact("cold_recovery.run_sha256", cold.get("run_sha256"),
          "0f77d954385f313a38622deed9fb4d76de3df532e53a6b26bd89d0d319be9314")
    exact("cold_recovery.artifact_manifest_sha256",
          cold.get("artifact_manifest_sha256"),
          "fb9ee4db14e0ccaf9904f5bbe5b7f54bc21553d06fd3b57ce813cd84be8110af")
    exact("cold_recovery.mode", cold.get("mode"), "recovery")
    exact("cold_recovery.generation", cold.get("generation"),
          revisit.get("generation_after"))
    exact("cold_recovery.observations", cold.get("observations"),
          revisit.get("current_unique"))
    exact("cold_recovery.status", cold.get("status"), "admitted")
    exact("cold_recovery.integrity", cold.get("integrity"), "valid")
    for field in ("fingerprint_matched", "mounted_read_only",
                  "read_only_guaranteed", "cleanup_complete"):
        exact(f"cold_recovery.{field}", cold.get(field), True)
    for field in ("write_enabled",):
        exact(f"cold_recovery.{field}", cold.get(field), False)
    for field in ("physical_write_calls", "blocked_write_attempts",
                  "transient_retries", "timeout_restarts", "owned_after"):
        exact(f"cold_recovery.{field}", cold.get(field), 0)
    exact("cold_recovery.attempts", cold.get("attempts"), 1)

    for parent, fields in (
            (candidate, ("firmware_sha256", "factory_sha256",
                         "app_elf_sha256", "map_sha256")),
            (automation, ("runner_sha256",)),
            (preflight, ("run_sha256", "artifact_manifest_sha256")),
            (visit_run, ("run_sha256", "artifact_manifest_sha256")),
            (cold, ("run_sha256", "artifact_manifest_sha256"))):
        for field in fields:
            value = parent.get(field, "")
            if not isinstance(value, str) or len(value) != 64:
                result.append(f"{field}: invalid SHA-256")

    for parent_name, parent in (
            ("visit_run", visit_run), ("cold_recovery", cold)):
        exact(f"{parent_name}.final_page", parent.get("final_page"), "home")
        exact(f"{parent_name}.final_owner", parent.get("final_owner"), "none")
        exact(f"{parent_name}.final_lease_mask",
              parent.get("final_lease_mask"), 0)
        exact(f"{parent_name}.final_safety_state",
              parent.get("final_safety_state"), "armed")
    exact("visit_run.hil_active_after", visit_run.get("hil_active_after"), False)

    privacy = record.get("privacy", {})
    exact("privacy.ambient_identifiers_retained",
          privacy.get("ambient_identifiers_retained"), False)
    exact("privacy.raw_radio_payloads_retained",
          privacy.get("raw_radio_payloads_retained"), False)
    exact("open_gates", record.get("open_gates"), [
        "route bounded native Field Survey artifact through Library/export",
        "route truthful local WiGLE 1.6 artifact without inventing UTC or location",
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
        "Field Survey visit acceptance passed: one-pass preflight, first/revisit "
        "generations 170->171->172, deterministic incomplete negative, exact "
        "read-only cold recovery and final Home/none/lease 0; export/station/GPS "
        "slices remain open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
