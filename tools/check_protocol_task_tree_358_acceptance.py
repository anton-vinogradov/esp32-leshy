#!/usr/bin/env python3
"""Fail closed unless the privacy-minimal dev.358 Protocol Workbench evidence is intact."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "tests/hil/evidence/board-01-protocol-task-tree-1.0.0-dev.358.json"
SOURCE = "738435159bc54aa2f99be2a869a2ccb2a521719f"


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def digest_shape(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def main() -> int:
    failures: list[str] = []
    value = json.loads(SUMMARY.read_text(encoding="utf-8"))
    candidate = value.get("candidate", {})
    require(
        failures,
        value.get("schema") == "leshy.protocol_workbench_hil.acceptance.v2"
        and value.get("status") == "pass_task_first_compare_decode_tft_review"
        and value.get("firmware_source_commit") == SOURCE,
        "summary/source identity mismatch",
    )
    require(
        failures,
        value.get("evidence_ids")
        == [
            "E-BUILD-232",
            "E-AUTO-208",
            "E-HIL-231",
            "E-UX-085",
            "E-STORAGE-076",
            "RB-M244",
        ],
        "evidence identifiers mismatch",
    )
    require(
        failures,
        candidate.get("version") == "1.0.0-dev.358"
        and candidate.get("firmware_bytes") == 3637536
        and candidate.get("factory_bytes") == 3703072
        and candidate.get("static_ram_bytes") == 234976
        and candidate.get("linked_flash_bytes") == 3637032
        and candidate.get("ota_slot_free_bytes") == 556768
        and all(
            digest_shape(candidate.get(field))
            for field in (
                "firmware_sha256",
                "factory_sha256",
                "app_elf_sha256",
                "map_sha256",
                "partitions_sha256",
            )
        ),
        "candidate identity/resource mismatch",
    )
    board = value.get("board", {})
    require(
        failures,
        board.get("id") == "board-01"
        and board.get("media_profile") == "media-01"
        and board.get("configured_identity_match") is True
        and board.get("raw_identifiers_retained") is False
        and not any(field in board for field in ("port", "mac", "exact_cid"))
        and board.get("candidate_flash_count") == 1
        and board.get("clone_port_touched") is False
        and board.get("cardputer_ports_opened") == 0
        and board.get("active_mac_wifi_touched") is False,
        "board isolation/privacy mismatch",
    )
    evidence = value.get("evidence", {})
    predecessor = evidence.get("rejected_predecessor", {})
    require(
        failures,
        all(
            digest_shape(evidence.get(field))
            for field in (
                "raw_run_sha256",
                "artifact_index_sha256",
                "runner_sha256",
                "checker_sha256",
            )
        )
        and predecessor.get("version") == "1.0.0-dev.357"
        and digest_shape(predecessor.get("raw_run_sha256")),
        "raw evidence/fail-closed lineage mismatch",
    )
    verified = value.get("verified", {})
    require(
        failures,
        verified.get("task_tree")
        == [
            "view_signal",
            "understand_parts/mark_parts",
            "understand_parts/read_marks",
            "compare_with_previous",
        ]
        and verified.get("fixture_source") == "retained_physical_nec_0.129"
        and verified.get("fixture_storage") == "bounded_ram_hil_only"
        and verified.get("fixture_pulses") == 67
        and verified.get("exact_tft_frames") == 14
        and verified.get("frame_format") == "rgb565be"
        and [verified.get("frame_width"), verified.get("frame_height")] == [240, 320],
        "task tree/fixture/TFT mismatch",
    )
    require(
        failures,
        verified.get("decode_outcome") == "complete"
        and verified.get("decode_fields") == 1
        and verified.get("decode_status") == "hil_ram_only"
        and verified.get("comparison_outcome") == "value_changed"
        and verified.get("comparison_regions") == 1
        and verified.get("comparison_status") == "hil_ram_only"
        and verified.get("decode_left_gutter_ink") == 0
        and verified.get("compare_left_gutter_ink") == 0
        and verified.get("visual_self_review")
        == "pass_no_clipping_overlap_or_orphaned_glyphs",
        "compare/decode result or visual-fit mismatch",
    )
    require(
        failures,
        verified.get("task_cursor_changed_pixels", 0) > 0
        and verified.get("task_cursor_outside_allowed_regions") == 0
        and verified.get("annotation_range_changed_pixels") == 429
        and verified.get("annotation_range_outside_allowed_regions") == 0
        and verified.get("raw_capture_mutated") is False,
        "dirty-region or source immutability mismatch",
    )
    require(
        failures,
        verified.get("product_storage_writes") == 0
        and verified.get("storage_generation_before")
        == verified.get("storage_generation_after") == 8
        and verified.get("storage_observations_before")
        == verified.get("storage_observations_after") == 54
        and verified.get("storage_physical_write_calls") == 0
        and verified.get("radio_tx_commands") == 0,
        "storage/radio isolation mismatch",
    )
    require(
        failures,
        verified.get("hil_sessions_begun") == 1
        and verified.get("hil_sessions_ended") == 1
        and verified.get("final_fixture_active") is False
        and verified.get("final_page") == "home"
        and verified.get("final_runtime_owner") == "none"
        and verified.get("final_lease_mask") == 0
        and verified.get("final_safety_state") == "armed"
        and verified.get("final_buzzer_inactive") is True
        and verified.get("final_nrf_ce_inactive") is True
        and verified.get("final_software_quiesce_complete") is True,
        "session/final cleanup mismatch",
    )
    require(
        failures,
        value.get("cadence", {}).get("accepted_deltas_after_anchor") == 1
        and value.get("cadence", {}).get("full_after_accepted_deltas") == 15
        and value.get("limitations", {}).get("real_capture_protected_commit_reopen")
        is False
        and value.get("limitations", {}).get("release_promotion") is False,
        "cadence/limitations mismatch",
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        json.dumps(
            {
                "schema": value["schema"],
                "status": value["status"],
                "version": candidate["version"],
                "source_commit": SOURCE,
                "sha256": hashlib.sha256(SUMMARY.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
