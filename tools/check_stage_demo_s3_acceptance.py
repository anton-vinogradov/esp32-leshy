#!/usr/bin/env python3
"""Fail closed unless retained exact-candidate DEMO-S3 evidence passes."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import masked_frame


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tests/hil/evidence/board-01-stage-demo-s3-0.70.json"
BUNDLE = ROOT / "tests/hil/evidence/board-01-stage-demo-s3-0.70"
SUITE = ROOT / "tests/hil/stage-demo-s3.v1.json"
GOLDEN_MANIFEST = (
    ROOT / "tests/hil/goldens/esp32-div-v2-n16/stage-s3-0.70-recording.json"
)
RUNNER_COMMIT = "6b602b6d31f0b95c57d46febf52257a829001043"
EXPECTED_RUNNER_SHA = "de014b2cd398d064ec9ace409be7ec44eb47761d05bc8ac489516ff3c01da61f"
EXPECTED_PRODUCT_RUNNER_SHA = (
    "3cc181648504fdf1fded23c73836ddaf38b0d3720558ea9a068c909622982506"
)
DOCS = (
    ROOT / "docs/v1/STATUS.md",
    ROOT / "docs/v1/STATUS.ru.md",
    ROOT / "docs/v1/STAGE_DEMO.md",
    ROOT / "docs/v1/STAGE_DEMO.ru.md",
    ROOT / "docs/v1/TRACEABILITY.md",
    ROOT / "docs/v1/TRACEABILITY.ru.md",
    ROOT / "docs/v1/DELIVERY_PLAN.md",
    ROOT / "docs/v1/DELIVERY_PLAN.ru.md",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def check_index(failures: list[str], root: Path, index: Path,
                required: set[str]) -> set[str]:
    indexed: set[str] = set()
    if not index.is_file():
        failures.append(f"artifact index missing: {index}")
        return indexed
    for line in index.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            failures.append(f"malformed artifact index line: {line!r}")
            continue
        expected, relative = parts
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            failures.append(f"artifact escapes bundle: {relative}")
            continue
        require(failures, path.is_file() and digest(path) == expected,
                f"artifact hash mismatch: {relative}")
        indexed.add(relative)
    require(failures, required <= indexed,
            f"artifact index lacks: {sorted(required - indexed)}")
    return indexed


def git_blob(path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{RUNNER_COMMIT}:{path}"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout


def main() -> int:
    failures: list[str] = []
    for path in (EVIDENCE, BUNDLE, SUITE, GOLDEN_MANIFEST):
        require(failures, path.exists(), f"required evidence missing: {path}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    evidence = load(EVIDENCE)
    require(failures, evidence.get("schema") ==
            "leshy.stage_demo_s3_acceptance.v1", "evidence schema mismatch")
    require(failures,
            evidence.get("status") == "pass_s3_stage_gate" and
            evidence.get("stage_gate_eligible") is True and
            evidence.get("release_gate_eligible") is False,
            "stage/release eligibility mismatch")
    require(failures, evidence.get("evidence_ids") == [
        "E-AUTO-035", "E-HIL-095", "E-SURVEY-008", "E-GATE-003"
    ], "evidence IDs mismatch")

    candidate = evidence.get("candidate", {})
    require(failures, candidate == {
        "version": "0.70.0-littlefs-reset-matrix",
        "source_commit": "35c8a94f0d2728d6c0d53a5eb413ddf1f4a08def",
        "firmware_sha256":
            "83dfc22bab7462a47cd329d6d7720dc8705bb9738ba08eb9fdc50e4df8f2468a",
        "factory_sha256":
            "8b808a78b4258625e96a5eee11be921982cedd0035f2a7d03ab45b1af4f770c6",
        "app_elf_sha256":
            "5ce796743f0282cc2d2f458e80ce405cf04acca9ac0c9c068f5e11605bd85efe",
        "map_sha256":
            "efdb876b37a9feb32390eed8aacad01a8e3d0dcaf2aae23e2a2784c56ac9975b",
        "linked_flash_bytes": 1165916,
        "static_ram_bytes": 134888,
        "app_image_bytes": 1166320,
        "factory_image_bytes": 1231856,
        "rtc_noinit_bytes": 60,
        "reproducible_rebuild": True,
    }, "candidate block mismatch")

    retained_firmware = BUNDLE / "product-run/firmware.bin"
    require(failures,
            retained_firmware.is_file() and
            retained_firmware.stat().st_size == candidate.get("app_image_bytes") and
            digest(retained_firmware) == candidate.get("firmware_sha256") and
            app_elf_sha256(retained_firmware) == candidate.get("app_elf_sha256"),
            "retained exact candidate mismatch")

    physical = evidence.get("physical", {})
    wrapper_run_path = BUNDLE / "run.json"
    wrapper_index = BUNDLE / "artifacts.sha256"
    product_run_path = BUNDLE / "product-run/run.json"
    product_index = BUNDLE / "product-run/artifacts.sha256"
    require(failures, digest(wrapper_run_path) == physical.get("run_sha256"),
            "wrapper run hash mismatch")
    require(failures, digest(wrapper_index) ==
            physical.get("artifact_index_sha256"), "wrapper index hash mismatch")
    require(failures, digest(product_run_path) ==
            physical.get("product_run_sha256"), "product run hash mismatch")
    require(failures, digest(product_index) ==
            physical.get("product_artifact_index_sha256"),
            "product index hash mismatch")
    wrapper_files = check_index(failures, BUNDLE, wrapper_index, {
        "run.json", "product-run/run.json",
        "product-run/firmware.bin", "product-run/boot-before.ndjson",
        "product-run/boot-after.ndjson",
    })
    product_files = check_index(failures, BUNDLE / "product-run", product_index, {
        "run.json", "firmware.bin", "boot-before.ndjson", "boot-after.ndjson",
    })
    require(failures,
            len([name for name in wrapper_files if name.endswith(".rgb565")]) == 5 and
            len([name for name in product_files if name.endswith(".rgb565")]) == 5,
            "five retained TFT framebuffer artifacts required")

    try:
        runner_blob = git_blob("tools/run_1x_stage_demo_s3_hil.py")
        product_runner_blob = git_blob("tools/run_1x_product_survey_hil.py")
        suite_blob = git_blob("tests/hil/stage-demo-s3.v1.json")
    except (OSError, subprocess.CalledProcessError) as error:
        failures.append(f"runner commit unavailable: {error}")
        runner_blob = product_runner_blob = suite_blob = b""
    require(failures, hashlib.sha256(runner_blob).hexdigest() ==
            physical.get("runner_sha256") == EXPECTED_RUNNER_SHA,
            "stage runner Git binding mismatch")
    require(failures, hashlib.sha256(product_runner_blob).hexdigest() ==
            physical.get("product_runner_sha256") == EXPECTED_PRODUCT_RUNNER_SHA,
            "product runner Git binding mismatch")
    require(failures, hashlib.sha256(suite_blob).hexdigest() ==
            physical.get("suite_sha256") == digest(SUITE),
            "suite Git/current binding mismatch")

    wrapper = load(wrapper_run_path)
    require(failures,
            wrapper.get("schema") == "leshy.stage_demo_s3.run.v1" and
            wrapper.get("mode") == "gate" and wrapper.get("passed") is True and
            wrapper.get("stage_gate_eligible") is True and
            wrapper.get("release_gate_eligible") is False and
            wrapper.get("failures") == [] and
            wrapper.get("candidate") == {
                "version": candidate["version"],
                "firmware_sha256": candidate["firmware_sha256"],
                "app_elf_sha256": candidate["app_elf_sha256"],
            } and
            wrapper.get("exact_cid") == physical.get("exact_cid") and
            wrapper.get("product_run_id") == physical.get("run_id") and
            wrapper.get("product_run_sha256") == physical.get("product_run_sha256"),
            "wrapper result/identity mismatch")
    comparisons = wrapper.get("comparisons", [])
    require(failures,
            [item.get("name") for item in comparisons] ==
            ["setup", "running", "detail", "committed", "export"] and
            all(item.get("passed") is True and
                item.get("mismatch_pixels") == 0 for item in comparisons),
            "five independent golden comparisons mismatch")

    suite = load(SUITE)
    golden_manifest = load(GOLDEN_MANIFEST)
    goldens = evidence.get("independent_goldens", {})
    require(failures, digest(GOLDEN_MANIFEST) ==
            goldens.get("recording_manifest_sha256"),
            "golden recording manifest hash mismatch")
    require(failures,
            golden_manifest.get("schema") ==
            "leshy.stage_demo_s3.golden_recording.v1" and
            golden_manifest.get("gate_eligible") is False and
            golden_manifest.get("manual_visual_review") == "pass" and
            golden_manifest.get("product_run_id") != wrapper.get("product_run_id") and
            golden_manifest.get("product_runner_sha256") ==
            physical.get("product_runner_sha256") and
            golden_manifest.get("candidate") == wrapper.get("candidate"),
            "independent recording/gate separation mismatch")
    manifest_by_name = {
        item.get("name"): item for item in golden_manifest.get("captures", [])
    }
    for capture in suite.get("captures", []):
        name = capture["name"]
        golden_path = (SUITE.parent / capture["golden"]).resolve()
        record = manifest_by_name.get(name, {})
        try:
            raw = zlib.decompress(golden_path.read_bytes())
        except (OSError, zlib.error) as error:
            failures.append(f"{name}: golden decode failed: {error}")
            continue
        require(failures,
                len(raw) == 153600 and digest(golden_path) ==
                record.get("golden_sha256") and
                hashlib.sha256(raw).hexdigest() == record.get("rgb565_sha256") and
                capture.get("mode") == record.get("mode") and
                capture.get("masks") == record.get("masks"),
                f"{name}: golden/suite/manifest binding mismatch")
        gate_raw = (BUNDLE / f"product-run/frames/{name}.rgb565").read_bytes()
        masks = capture["masks"] if capture["mode"] == "masked_exact" else []
        require(failures,
                masked_frame(gate_raw, 240, 320, masks) ==
                masked_frame(raw, 240, 320, masks),
                f"{name}: independent framebuffer comparison failed")

    product = load(product_run_path)
    before = product.get("boot_before", {})
    after = product.get("boot_after", {})
    committed = product.get("committed", {})
    export = product.get("library_export", {})
    final = product.get("final_state", {})
    require(failures,
            product.get("passed") is True and product.get("gate_eligible") is True and
            product.get("failures") == [] and
            product.get("candidate", {}).get("flashed") is True and
            product.get("candidate", {}).get("firmware_sha256") ==
            candidate.get("firmware_sha256") and
            product.get("candidate", {}).get("app_elf_sha256") ==
            candidate.get("app_elf_sha256") and
            product.get("expected_cid") == physical.get("exact_cid"),
            "inner product run mismatch")
    require(failures,
            before.get("recovery", {}).get("generation") == 69 and
            after.get("recovery", {}).get("generation") == 70 and
            before.get("recovery", {}).get("physical_write_calls") == 0 and
            after.get("recovery", {}).get("physical_write_calls") == 0 and
            committed.get("survey_generation") == 70 and
            committed.get("survey_observations") == 29 and
            committed.get("survey_scan_accepted") == 29 and
            committed.get("survey_forwarded") == 29 and
            committed.get("survey_dropped") == 0 and
            export.get("status") == "valid" and export.get("generation") == 70 and
            export.get("persistent") is True and export.get("simulated") is False and
            export.get("radio_touched") is False and
            final.get("page") == "home" and final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0,
            "product continuity/export/final cleanup mismatch")
    before_heap = before.get("ready", {})
    after_heap = after.get("ready", {})
    require(failures,
            [before_heap.get("heap_total"), before_heap.get("heap_free"),
             before_heap.get("heap_min_free")] ==
            [after_heap.get("heap_total"), after_heap.get("heap_free"),
             after_heap.get("heap_min_free")] == [266616, 202200, 182148],
            "heap invariance mismatch")
    require(failures, evidence.get("s3_criteria") == {
        "1_clean_boot_probe": "pass", "2_user_start": "pass",
        "3_passive_normalized_observations": "pass",
        "4_list_detail_back": "pass", "5_atomic_stop_commit": "pass",
        "6_reboot_offline_reopen": "pass",
        "7_json_summary_export": "pass", "8_host_and_hil_coverage": "pass",
        "9_missing_source_visible_zero_lease": "pass",
    }, "S3 criteria mismatch")
    require(failures, evidence.get("stage_state") == {
        "s3": "done", "s4": "active",
        "physical_power_cut": "required_by_demo_s4",
        "eight_hour_cross_radio_endurance": "required_by_demo_s4",
    }, "stage transition mismatch")

    for doc in DOCS:
        source = doc.read_text(encoding="utf-8")
        require(failures,
                "E-GATE-003" in source and "E-HIL-095" in source,
                f"S3 gate documentation marker missing: {doc.name}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("DEMO-S3 acceptance passed: exact 0.70, generation 69->70, "
          "29/29 observations, five independent TFT matches, S4 active")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
