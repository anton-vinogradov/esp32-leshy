#!/usr/bin/env python3
"""Machine-check retained exact-candidate S3 product progress evidence."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-s3-product-regression-0.58.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-s3-product-regression-0.58"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    evidence = load(EVIDENCE)
    require(failures, evidence.get("schema") == "leshy.s3_product_progress.v1",
            "evidence schema mismatch")
    require(failures,
            evidence.get("status") == "pass_progress_not_stage_gate" and
            evidence.get("runner_gate_eligible") is True and
            evidence.get("stage_gate_eligible") is False and
            evidence.get("release_gate_eligible") is False,
            "progress/stage/release eligibility mismatch")
    require(failures, evidence.get("evidence_ids") == ["E-AUTO-023", "E-HIL-083"],
            "evidence IDs mismatch")
    runner_commit = "d31e08f05c6679a13b6555078d58e8afdeb24bef"
    require(failures, evidence.get("runner_source_commit") == runner_commit,
            "runner source commit mismatch")
    try:
        runner_source = subprocess.run(
            ["git", "show", f"{runner_commit}:tools/run_1x_product_survey_hil.py"],
            cwd=ROOT, check=True, capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        failures.append(f"runner source Git object unavailable: {error}")
        runner_source = b""
    require(failures,
            hashlib.sha256(runner_source).hexdigest() ==
            evidence.get("runner_source_sha256") ==
            "fdef8ee63dc71d0c2fe034a59a24c86896d83e0b81abf15c5f11b36d035efa4d" and
            evidence.get("runner_source_binding") ==
            "retrospective_git_object_not_runtime_emitted",
            "runner source object/hash/trust binding mismatch")

    candidate = evidence.get("candidate", {})
    firmware = BUNDLE / "firmware.bin"
    require(failures,
            candidate.get("version") == "0.58.0-stage-demo-s2-measure" and
            candidate.get("firmware_sha256") ==
            "b4d854f4735e2fb83f202169951107a7a8c9a7f97beb07d0af7c1cf3e45dc50a" and
            candidate.get("app_elf_sha256") ==
            "ec12011c7134e08aa857e6209e846b29d41428a1dcad98840c69c09d80e85d4f" and
            candidate.get("flashed_and_verified") is True and
            firmware.is_file() and digest(firmware) == candidate.get("firmware_sha256") and
            app_elf_sha256(firmware) == candidate.get("app_elf_sha256"),
            "exact retained candidate mismatch")

    retained = evidence.get("retained", {})
    run_path = BUNDLE / "run.json"
    index_path = BUNDLE / "artifacts.sha256"
    require(failures, digest(run_path) == retained.get("run_sha256"),
            "run hash mismatch")
    require(failures, digest(index_path) == retained.get("artifact_index_sha256"),
            "artifact index hash mismatch")
    indexed: set[str] = set()
    for line in index_path.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            failures.append("malformed artifact index line")
            continue
        expected, relative = parts
        path = (BUNDLE / relative).resolve()
        try:
            path.relative_to(BUNDLE.resolve())
        except ValueError:
            failures.append(f"artifact escapes bundle: {relative}")
            continue
        require(failures, path.is_file() and digest(path) == expected,
                f"artifact hash mismatch: {relative}")
        indexed.add(relative)
    require(failures,
            {"firmware.bin", "run.json", "boot-before.ndjson", "boot-after.ndjson"}
            <= indexed and len([name for name in indexed if name.endswith(".rgb565")]) == 5,
            "artifact index incomplete")

    run = load(run_path)
    require(failures,
            run.get("passed") is True and run.get("gate_eligible") is True and
            run.get("failures") == [] and run.get("run_id") == evidence["run"]["run_id"] and
            run.get("candidate", {}).get("flashed") is True and
            run.get("candidate", {}).get("firmware_sha256") ==
            candidate.get("firmware_sha256") and
            run.get("candidate", {}).get("app_elf_sha256") ==
            candidate.get("app_elf_sha256") and
            run.get("expected_cid") == evidence["run"]["exact_cid"],
            "runner identity/result mismatch")

    before = run.get("boot_before", {}).get("recovery", {})
    after = run.get("boot_after", {}).get("recovery", {})
    cid = evidence["run"]["exact_cid"]
    for name, record, generation in (("before", before, 65), ("after", after, 66)):
        require(failures,
                record.get("status") == "admitted" and
                record.get("expected_fingerprint") == cid and
                record.get("observed_fingerprint") == cid and
                record.get("generation") == generation and
                record.get("attempts") == 1 and record.get("transient_retries") == 0 and
                record.get("blocked_write_attempts") == 0 and
                record.get("physical_write_calls") == 0 and
                record.get("cleanup_complete") is True and
                record.get("owned_after") == 0,
                f"{name} boot recovery mismatch")

    running = run.get("running", {})
    detail = run.get("running_detail", {})
    returned = run.get("running_list_after_detail", {})
    require(failures,
            running.get("survey_scan_accepted") == 10 and
            running.get("survey_forwarded") == 10 and
            running.get("survey_dropped") == 0 and
            running.get("survey_queue_depth") == 0 and
            running.get("survey_product_backend_open") is True and
            running.get("survey_running") is True,
            "real passive running accounting mismatch")
    require(failures,
            detail.get("survey_view") == "detail" and
            detail.get("survey_running") is True and
            detail.get("survey_observations") == 10 and
            returned.get("survey_view") == "list" and
            returned.get("survey_running") is True and
            returned.get("survey_observations") == 10 and
            0 < run.get("detail_back_ack_ms", 999) <= 150,
            "List/Detail/Back continuity or latency mismatch")

    committed = run.get("committed", {})
    export = run.get("library_export", {})
    final = run.get("final_state", {})
    require(failures,
            committed.get("survey_generation") == 66 and
            committed.get("survey_observations") == 10 and
            committed.get("survey_product_status") == "committed" and
            committed.get("survey_product_backend_open") is False and
            committed.get("survey_product_cleanup_complete") is True and
            export.get("status") == "valid" and export.get("generation") == 66 and
            export.get("persistent") is True and export.get("simulated") is False and
            export.get("radio_touched") is False and
            export.get("session", {}).get("observations") == 10 and
            final.get("page") == "home" and final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "commit/reboot/export/final cleanup mismatch")

    captures = run.get("captures", {})
    states = ["setup", "running", "detail", "committed", "export"]
    require(failures, sorted(captures) == sorted(states), "capture set mismatch")
    for state in states:
        record = captures.get(state, {})
        raw = BUNDLE / f"frames/{state}.rgb565"
        png = BUNDLE / f"frames/{state}.png"
        require(failures,
                raw.is_file() and raw.stat().st_size == 153600 and
                digest(raw) == record.get("rgb565_sha256") and
                png.is_file() and digest(png) == record.get("png_sha256") and
                record.get("frame_begin", {}).get("revision") ==
                record.get("frame_end", {}).get("revision") ==
                record.get("state", {}).get("revision"),
                f"{state}: retained TFT capture mismatch")

    summary = evidence.get("run", {})
    require(failures, summary == {
        "run_id": run.get("run_id"),
        "exact_cid": run.get("expected_cid"),
        "generation_before": before.get("generation"),
        "generation_after": after.get("generation"),
        "observations": committed.get("survey_observations"),
        "accepted": running.get("survey_scan_accepted"),
        "forwarded": running.get("survey_forwarded"),
        "drops": running.get("survey_dropped"),
        "detail_back_ack_ms": run.get("detail_back_ack_ms"),
        "captures": len(captures),
        "final_page": final.get("page"),
        "final_owner": final.get("runtime_owner"),
        "final_lease_mask": final.get("lease_mask"),
    }, "evidence run summary is not exactly derived from retained run")

    criteria = evidence.get("s3_criteria", {})
    require(failures, criteria == {
        "1_clean_boot_probe": "pass",
        "2_user_start": "pass",
        "3_passive_normalized_observations": "pass",
        "4_list_detail_back": "pass",
        "5_atomic_stop_commit": "pass_software_reset_only",
        "6_reboot_offline_reopen": "pass",
        "7_json_summary_export": "pass",
        "8_host_and_hil_coverage": "pass",
        "9_missing_source_visible_zero_lease": "partial_host_contract_only",
    },
            "S3 criteria state mismatch")
    require(failures, evidence.get("open_gate_work") == [
        "missing_source_real_tft", "physical_power_cut", "littlefs_parity",
        "independent_demo_goldens",
    ], "open S3 gate work mismatch")
    require(failures, evidence.get("visual_review") == {
        "manual_review": "pass", "independent_goldens": False,
        "states": states,
    }, "visual review scope mismatch")

    if failures:
        for failure in failures:
            print(f"S3 product progress failed: {failure}", file=sys.stderr)
        return 1
    print(
        "S3 product progress passed: generation 65->66, passive 10/10, "
        "Detail/Back 102.636 ms, reboot/export valid, stage gate still open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
