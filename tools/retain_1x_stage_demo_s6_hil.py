#!/usr/bin/env python3
"""Validate and compact an exact physical DEMO-S6 run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import run_1x_stage_demo_s6_hil as stage


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "leshy.hil.stage_demo_s6.acceptance.v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    output = args.output.resolve()
    if output.exists():
        parser.error("output must not exist")

    parent_path = run_dir / "run.json"
    targets_path = run_dir / "targets-evidence/run.json"
    companion_path = run_dir / "companion-offline/run.json"
    manifest_path = run_dir / "artifacts.sha256"
    for path in (parent_path, targets_path, companion_path, manifest_path):
        if not path.is_file():
            parser.error(f"required record missing: {path}")

    parent = load(parent_path)
    targets = load(targets_path)
    companion = load(companion_path)
    lineage = parent.get("installation", {}).get(
        "reused_survey_lineage", {})
    survey_root = Path(str(lineage.get("path", "")))
    baseline_path = survey_root / "baseline-survey/run.json"
    repeat_path = survey_root / "repeat-survey/run.json"
    if not baseline_path.is_file() or not repeat_path.is_file():
        parser.error("reused Survey records are unavailable")
    baseline = load(baseline_path)
    repeat = load(repeat_path)

    expected = parent.get("candidate", {})
    summary, failures = stage.validate_children(
        baseline, repeat, targets, companion, expected,
        stage.EXPECTED_CID, parent.get("source_commit", ""),
        baseline_flashed=False,
    )
    children = parent.get("children", {})
    if not (
        parent.get("schema") == stage.SCHEMA
        and parent.get("status") == "pass_demo_path"
        and parent.get("passed") is True
        and parent.get("demo_path_eligible") is True
        and parent.get("failures") == []
        and parent.get("summary") == summary
        and parent.get("installation", {}).get(
            "application_flash_count") == 0
        and parent.get("installation", {}).get(
            "exact_flash_reused") is True
        and children.get("baseline-survey", {}).get("reused") is True
        and children.get("repeat-survey", {}).get("reused") is True
        and children.get("targets-evidence", {}).get("exit_code") == 0
        and children.get("companion-offline", {}).get("exit_code") == 0
        and children.get("baseline-survey", {}).get("run_sha256") ==
            digest(baseline_path)
        and children.get("repeat-survey", {}).get("run_sha256") ==
            digest(repeat_path)
        and children.get("targets-evidence", {}).get("run_sha256") ==
            digest(targets_path)
        and children.get("companion-offline", {}).get("run_sha256") ==
            digest(companion_path)
    ):
        failures.append("parent status/reuse/child hash mismatch")

    target_list = targets.get("targets", {}).get("list", {})
    target_released = targets.get("targets", {}).get("released", {})
    target_cleanup = targets.get("cleanup", {})
    companion_cleanup = companion.get("cleanup", {})
    target_rows = targets.get("targets", {}).get("rows", [])
    target_details = targets.get("targets", {}).get("evidence_details", [])
    if not (
        target_list.get("read_only") is False
        and target_list.get("write_enabled") is False
        and target_list.get("blocked_write_attempts") == 0
        and target_list.get("filesystem_mount_error") == 0
        and target_list.get("cleanup_complete") is True
        and target_released.get("status") == "not_loaded"
        and target_released.get("heap_free_after_release") >=
            target_released.get("heap_free_before", 1) - 512
        and target_cleanup.get("complete") is True
        and companion_cleanup.get("complete") is True
    ):
        failures.append("Targets mutation semantics/release/final cleanup mismatch")
    if failures:
        raise SystemExit("FAIL: " + "; ".join(failures))

    snapshot = companion["offline_snapshot"]
    final = companion_cleanup["final_state"]
    evidence = {
        "schema": SCHEMA,
        "status": "pass_demo_path",
        "evidence_ids": ["E-AUTO-132", "E-HIL-189", "E-DEMO-006"],
        "board": "board-01",
        "port": parent["target"]["port"],
        "rom_mac": "1c:db:d4:87:90:d4",
        "exact_cid": stage.EXPECTED_CID,
        "candidate": expected,
        "firmware_source_commit":
            "e04d98dd3c5e5d494c615e12f2897dc3207272a9",
        "verification_source_commit": parent["source_commit"],
        "installation": {
            "candidate_application_flashes_total": 1,
            "application_flashes_for_demo_continuation": 0,
            "exact_flash_reused": True,
            "survey_children_reused": True,
        },
        "survey_pair": {
            "generation_pair": [
                summary["baseline_generation"],
                summary["repeat_generation"],
            ],
            "observations": [
                baseline["committed"]["survey_observations"],
                repeat["committed"]["survey_observations"],
            ],
            "baseline_run_sha256": digest(baseline_path),
            "repeat_run_sha256": digest(repeat_path),
            "both_passed": True,
            "both_no_flash": True,
            "both_final_cleanup_complete": True,
        },
        "targets": {
            "catalog_targets": summary["targets"],
            "comparison_items": summary["comparison_items"],
            "comparison_classes": [
                item["selected_change_class"] for item in target_rows
            ],
            "evidence_views_opened": summary["evidence_views_opened"],
            "evidence_selections": [
                item["comparison_selection"] for item in target_details
            ],
            "mutation_capable": target_list["read_only"] is False,
            "write_in_flight": target_list["write_enabled"],
            "blocked_write_attempts": target_list["blocked_write_attempts"],
            "filesystem_mount_error": target_list["filesystem_mount_error"],
            "storage_write_calls": targets["storage_write_calls"],
            "radio_tx_commands": targets["radio_tx_commands"],
            "heap_free_before": target_released["heap_free_before"],
            "heap_free_after_release":
                target_released["heap_free_after_release"],
        },
        "offline_companion": {
            "protocol": companion["connection"]["protocol"],
            "transport": companion["connection"]["transport"],
            "sessions": snapshot["counts"]["sessions"],
            "targets": snapshot["counts"]["targets"],
            "comparison_items": snapshot["counts"]["comparison_items"],
            "snapshot_bytes": snapshot["bytes"],
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_sha256": snapshot["sha256"],
            "canonical_round_trip": snapshot["canonical_round_trip"],
            "search_fields": [
                item["field"] for item in snapshot["search_proofs"]
            ],
            "search_matches": [
                item["matches"] for item in snapshot["search_proofs"]
            ],
        },
        "isolation": {
            "opened_ports": parent["target"]["ports_opened"],
            "cardputer_ports_opened":
                parent["target"]["cardputer_ports_opened"],
            "serial_port_discovery_calls":
                parent["target"]["serial_port_discovery_calls"],
            "host_network_tools_invoked":
                parent["transport"]["host_network_tools_invoked"],
            "active_mac_wifi_touched":
                parent["transport"]["active_mac_wifi_touched"],
            "wifi_softap_started":
                parent["transport"]["wifi_softap_started"],
        },
        "final_safety": {
            "page": final["page"],
            "runtime_owner": final["runtime_owner"],
            "lease_mask": final["lease_mask"],
            "safety_state": final["safety_state"],
            "safety_latched": final["safety_latched"],
            "targets_cleanup_complete": target_cleanup["complete"],
            "companion_cleanup_complete": companion_cleanup["complete"],
        },
        "raw_hashes": {
            "parent_run_sha256": digest(parent_path),
            "targets_run_sha256": digest(targets_path),
            "companion_run_sha256": digest(companion_path),
            "manifest_sha256": digest(manifest_path),
            "stage_runner_sha256": digest(
                ROOT / "tools/run_1x_stage_demo_s6_hil.py"),
            "targets_runner_sha256": digest(
                ROOT / "tools/run_1x_targets_evidence_hil.py"),
            "companion_runner_sha256": digest(
                ROOT / "tools/run_1x_companion_usb_delta_hil.py"),
        },
        "cadence": {
            "accepted_deltas_since_full": 5,
            "full_gate_at": 15,
            "advanced_by_demo_reuse": False,
        },
        "s6_exit_eligible": False,
        "remaining_blockers": parent["s6_exit_blockers"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": evidence["status"],
        "output": str(output),
        "snapshot_id": snapshot["snapshot_id"],
        "comparison_items": summary["comparison_items"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
