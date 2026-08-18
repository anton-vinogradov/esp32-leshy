#!/usr/bin/env python3
"""Record independent TFT goldens or run the exact DEMO-S3 product gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import masked_frame


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_RUNNER = ROOT / "tools/run_1x_product_survey_hil.py"
RUN_SCHEMA = "leshy.stage_demo_s3.run.v1"
MANIFEST_SCHEMA = "leshy.stage_demo_s3.golden_recording.v1"
WIDTH = 240
HEIGHT = 320
FRAME_BYTES = WIDTH * HEIGHT * 2
CAPTURE_NAMES = ["setup", "running", "detail", "committed", "export"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def suite_child(suite_path: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("suite path is missing")
    resolved = (suite_path.parent / relative).resolve()
    try:
        resolved.relative_to(suite_path.parent.resolve())
    except ValueError as error:
        raise ValueError(f"suite path escapes tests/hil: {relative}") from error
    return resolved


def validate_suite(path: Path) -> dict[str, Any]:
    suite = load_json(path)
    if suite.get("schema") != "leshy.stage_demo_s3.suite.v1":
        raise ValueError("suite schema mismatch")
    if suite.get("id") != "stage-demo-s3" or suite.get("revision") != 1:
        raise ValueError("suite identity mismatch")
    captures = suite.get("captures")
    if (not isinstance(captures, list) or
            [item.get("name") for item in captures] != CAPTURE_NAMES):
        raise ValueError("suite must contain the five ordered DEMO-S3 captures")
    for capture in captures:
        if capture.get("mode") not in ("exact", "masked_exact"):
            raise ValueError(f"{capture.get('name')}: unsupported comparison mode")
        masks = capture.get("masks")
        if not isinstance(masks, list):
            raise ValueError(f"{capture.get('name')}: masks must be a list")
        for mask in masks:
            if (not isinstance(mask, list) or len(mask) != 4 or
                    not all(isinstance(value, int) for value in mask)):
                raise ValueError(f"{capture.get('name')}: invalid mask")
            x, y, width, height = mask
            if (x < 0 or y < 0 or width <= 0 or height <= 0 or
                    x + width > WIDTH or y + height > HEIGHT):
                raise ValueError(f"{capture.get('name')}: mask is out of bounds")
    suite_child(path, suite.get("recording_manifest"))
    for capture in captures:
        suite_child(path, capture.get("golden"))
    return suite


def validate_product_run(bundle: Path, firmware: Path, expected_version: str,
                         expected_cid: str) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    run_path = bundle / "run.json"
    if not run_path.is_file():
        return {}, ["product run.json missing"]
    run = load_json(run_path)
    candidate = run.get("candidate", {})
    if (run.get("schema") != "leshy.product_survey_hil.run.v1" or
            run.get("passed") is not True or run.get("gate_eligible") is not True or
            run.get("failures") != []):
        failures.append("product run did not pass its exact-candidate gate")
    if candidate != {
        "firmware_sha256": digest(firmware),
        "app_elf_sha256": app_elf_sha256(firmware),
        "version": expected_version,
        "flashed": True,
    }:
        failures.append("product candidate identity mismatch")
    if run.get("expected_cid") != expected_cid:
        failures.append("product exact CID mismatch")
    captures = run.get("captures")
    if not isinstance(captures, dict) or sorted(captures) != sorted(CAPTURE_NAMES):
        failures.append("product capture set mismatch")
        captures = {}
    for name, record in captures.items():
        raw = bundle / "frames" / f"{name}.rgb565"
        png = bundle / "frames" / f"{name}.png"
        if (not raw.is_file() or raw.stat().st_size != FRAME_BYTES or
                digest(raw) != record.get("rgb565_sha256") or
                not png.is_file() or digest(png) != record.get("png_sha256") or
                record.get("frame_begin", {}).get("revision") !=
                record.get("frame_end", {}).get("revision") or
                record.get("frame_begin", {}).get("revision") !=
                record.get("state", {}).get("revision")):
            failures.append(f"{name}: product capture/hash/revision mismatch")
    final = run.get("final_state", {})
    if not (final.get("page") == "home" and
            final.get("runtime_owner") == "none" and final.get("lease_mask") == 0):
        failures.append("product final cleanup mismatch")
    return run, failures


def mismatch_pixels(actual: bytes, expected: bytes) -> int:
    if len(actual) != len(expected):
        return max(len(actual), len(expected)) // 2
    return sum(
        actual[offset:offset + 2] != expected[offset:offset + 2]
        for offset in range(0, len(actual), 2)
    )


def record_goldens(suite_path: Path, suite: dict[str, Any], product: Path,
                   run: dict[str, Any], firmware: Path) -> dict[str, Any]:
    manifest_path = suite_child(suite_path, suite["recording_manifest"])
    if manifest_path.exists():
        raise FileExistsError(f"recording manifest already exists: {manifest_path}")
    records: list[dict[str, Any]] = []
    for capture in suite["captures"]:
        name = capture["name"]
        raw_path = product / "frames" / f"{name}.rgb565"
        golden = suite_child(suite_path, capture["golden"])
        if golden.exists():
            raise FileExistsError(f"golden already exists: {golden}")
        raw = raw_path.read_bytes()
        compressed = zlib.compress(raw, level=9)
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_bytes(compressed)
        if zlib.decompress(golden.read_bytes()) != raw:
            raise RuntimeError(f"{name}: recorded golden round-trip mismatch")
        records.append({
            "name": name,
            "mode": capture["mode"],
            "masks": capture["masks"],
            "rgb565_sha256": hashlib.sha256(raw).hexdigest(),
            "golden_sha256": hashlib.sha256(compressed).hexdigest(),
        })
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "suite_id": suite["id"],
        "suite_revision": suite["revision"],
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "manual_visual_review": "pass",
        "gate_eligible": False,
        "product_run_id": run.get("run_id"),
        "product_run_sha256": digest(product / "run.json"),
        "product_runner_sha256": digest(PRODUCT_RUNNER),
        "candidate": {
            "version": run.get("candidate", {}).get("version"),
            "firmware_sha256": digest(firmware),
            "app_elf_sha256": app_elf_sha256(firmware),
        },
        "captures": records,
    }
    write_json(manifest_path, manifest)
    return manifest


def compare_goldens(suite_path: Path, suite: dict[str, Any], product: Path,
                    run: dict[str, Any], firmware: Path) -> tuple[list[dict[str, Any]], list[str]]:
    failures: list[str] = []
    manifest_path = suite_child(suite_path, suite["recording_manifest"])
    if not manifest_path.is_file():
        return [], ["independent golden recording manifest missing"]
    manifest = load_json(manifest_path)
    candidate = manifest.get("candidate", {})
    if (manifest.get("schema") != MANIFEST_SCHEMA or
            manifest.get("gate_eligible") is not False or
            manifest.get("manual_visual_review") != "pass"):
        failures.append("golden recording trust/status mismatch")
    if candidate != {
        "version": run.get("candidate", {}).get("version"),
        "firmware_sha256": digest(firmware),
        "app_elf_sha256": app_elf_sha256(firmware),
    }:
        failures.append("golden candidate differs from gate candidate")
    if manifest.get("product_runner_sha256") != digest(PRODUCT_RUNNER):
        failures.append("product runner differs from golden recording")
    if manifest.get("product_run_id") == run.get("run_id"):
        failures.append("gate run reuses the golden recording run")
    manifest_by_name = {
        item.get("name"): item for item in manifest.get("captures", [])
        if isinstance(item, dict)
    }
    comparisons: list[dict[str, Any]] = []
    for capture in suite["captures"]:
        name = capture["name"]
        golden_path = suite_child(suite_path, capture["golden"])
        actual_path = product / "frames" / f"{name}.rgb565"
        if not golden_path.is_file() or not actual_path.is_file():
            failures.append(f"{name}: actual or golden frame missing")
            continue
        compressed = golden_path.read_bytes()
        try:
            expected = zlib.decompress(compressed)
        except zlib.error as error:
            failures.append(f"{name}: invalid golden compression: {error}")
            continue
        actual = actual_path.read_bytes()
        recorded = manifest_by_name.get(name, {})
        if (recorded.get("golden_sha256") != hashlib.sha256(compressed).hexdigest() or
                recorded.get("rgb565_sha256") != hashlib.sha256(expected).hexdigest() or
                recorded.get("mode") != capture["mode"] or
                recorded.get("masks") != capture["masks"]):
            failures.append(f"{name}: golden manifest binding mismatch")
        masks = capture["masks"] if capture["mode"] == "masked_exact" else []
        masked_actual = masked_frame(actual, WIDTH, HEIGHT, masks)
        masked_expected = masked_frame(expected, WIDTH, HEIGHT, masks)
        mismatch = mismatch_pixels(masked_actual, masked_expected)
        passed = mismatch == 0
        if not passed:
            failures.append(f"{name}: {mismatch} unmasked pixels differ")
        comparisons.append({
            "name": name,
            "mode": capture["mode"],
            "masks": masks,
            "passed": passed,
            "mismatch_pixels": mismatch,
            "actual_sha256": hashlib.sha256(actual).hexdigest(),
            "golden_sha256": hashlib.sha256(compressed).hexdigest(),
        })
    if len(comparisons) != len(suite["captures"]):
        failures.append("comparison set incomplete")
    return comparisons, failures


def artifact_manifest(output: Path) -> None:
    lines: list[str] = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "artifacts.sha256":
            lines.append(f"{digest(path)}  {path.relative_to(output)}")
    (output / "artifacts.sha256").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def run_product(args: argparse.Namespace, product: Path) -> tuple[int, str]:
    command = [
        sys.executable, str(PRODUCT_RUNNER),
        "--port", args.port,
        "--firmware", str(args.firmware),
        "--expected-version", args.expected_version,
        "--expected-cid", args.expected_cid,
        "--output", str(product),
        "--boot-seconds", str(args.boot_seconds),
    ]
    if args.flash:
        command.append("--flash")
    process = subprocess.run(command, cwd=ROOT, check=False,
                             capture_output=True, text=True)
    return process.returncode, process.stdout + process.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--record-goldens", action="store_true")
    parser.add_argument("--adopt-product-run", type=Path)
    parser.add_argument("--boot-seconds", type=float, default=20.0)
    args = parser.parse_args()
    args.firmware = args.firmware.resolve()
    args.suite = args.suite.resolve()
    args.output = args.output.resolve()
    if not args.firmware.is_file():
        parser.error("firmware not found")
    if args.output.exists():
        parser.error("output must not exist")
    if args.adopt_product_run is not None and not args.record_goldens:
        parser.error("--adopt-product-run is recording-only")
    if args.adopt_product_run is not None and args.flash:
        parser.error("adopted recording cannot flash")
    if args.adopt_product_run is None and (not args.port or not args.flash):
        parser.error("physical recording/gate run requires --port and --flash")

    suite = validate_suite(args.suite)
    args.output.mkdir(parents=True)
    product = args.output / "product-run"
    runner_log = ""
    product_exit = 0
    if args.adopt_product_run is not None:
        shutil.copytree(args.adopt_product_run.resolve(), product)
    else:
        product_exit, runner_log = run_product(args, product)
    (args.output / "product-runner.log").write_text(runner_log, encoding="utf-8")

    run, failures = validate_product_run(
        product, args.firmware, args.expected_version, args.expected_cid
    )
    if product_exit != 0:
        failures.append(f"product runner exit: {product_exit}")
    manifest: dict[str, Any] = {}
    comparisons: list[dict[str, Any]] = []
    if not failures:
        if args.record_goldens:
            manifest = record_goldens(
                args.suite, suite, product, run, args.firmware
            )
        else:
            comparisons, compare_failures = compare_goldens(
                args.suite, suite, product, run, args.firmware
            )
            failures.extend(compare_failures)
    result = {
        "schema": RUN_SCHEMA,
        "suite_id": suite["id"],
        "suite_revision": suite["revision"],
        "runner_sha256": digest(Path(__file__).resolve()),
        "product_runner_sha256": digest(PRODUCT_RUNNER),
        "suite_sha256": digest(args.suite),
        "mode": "record_goldens" if args.record_goldens else "gate",
        "passed": not failures,
        "stage_gate_eligible": (not args.record_goldens and not failures),
        "release_gate_eligible": False,
        "failures": failures,
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": digest(args.firmware),
            "app_elf_sha256": app_elf_sha256(args.firmware),
        },
        "exact_cid": args.expected_cid,
        "product_run_id": run.get("run_id"),
        "product_run_sha256": (
            digest(product / "run.json") if (product / "run.json").is_file() else ""
        ),
        "golden_recording": manifest,
        "comparisons": comparisons,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(args.output / "run.json", result)
    artifact_manifest(args.output)
    print(json.dumps({
        "output": str(args.output),
        "passed": result["passed"],
        "stage_gate_eligible": result["stage_gate_eligible"],
        "failures": failures,
    }, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
