#!/usr/bin/env python3
"""Run a manifest-driven smoke suite against an exact ESP32-Leshy candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import subprocess
import sys
import time
import zlib
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


SUITE_SCHEMA = "leshy.prerelease.suite.v1"
RUN_SCHEMA = "leshy.prerelease.run.v2"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_suite(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != SUITE_SCHEMA:
        raise ValueError(f"suite must use schema {SUITE_SCHEMA}")
    if not isinstance(value.get("id"), str) or not value["id"]:
        raise ValueError("suite id is required")
    if not isinstance(value.get("revision"), int) or value["revision"] <= 0:
        raise ValueError("suite revision must be a positive integer")
    if not isinstance(value.get("boot_assert"), dict):
        raise ValueError("suite boot_assert is required")
    scenarios = value.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("suite must contain at least one scenario")
    seen: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str):
            raise ValueError("every scenario needs an id")
        if scenario["id"] in seen:
            raise ValueError(f"duplicate scenario id: {scenario['id']}")
        seen.add(scenario["id"])
        steps = scenario.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"scenario {scenario['id']} has no steps")
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get("id"), str):
                raise ValueError(f"scenario {scenario['id']} has a step without id")
            action = step.get("action")
            if action is not None and action not in {
                "up", "down", "left", "right", "select", "back"
            }:
                raise ValueError(f"unsupported action in {step['id']}: {action}")
            if not isinstance(step.get("assert"), dict):
                raise ValueError(f"step {step['id']} needs assertions")
            capture = step.get("capture")
            if capture is not None:
                if not isinstance(capture, dict) or not isinstance(
                    capture.get("golden"), str
                ):
                    raise ValueError(f"step {step['id']} capture needs a golden")
                if capture.get("mode", "exact") not in {"exact", "masked_exact"}:
                    raise ValueError(f"unsupported visual mode in {step['id']}")
    return value


def _operator_failures(expected: dict[str, Any], actual: Any, path: str) -> list[str]:
    failures: list[str] = []
    for operator, operand in expected.items():
        if operator == "$eq" and actual != operand:
            failures.append(f"{path}: {actual!r} != {operand!r}")
        elif operator == "$gte" and not (
            isinstance(actual, (int, float)) and actual >= operand
        ):
            failures.append(f"{path}: {actual!r} is not >= {operand!r}")
        elif operator == "$lte" and not (
            isinstance(actual, (int, float)) and actual <= operand
        ):
            failures.append(f"{path}: {actual!r} is not <= {operand!r}")
        elif operator == "$in" and not (
            isinstance(operand, list) and actual in operand
        ):
            failures.append(f"{path}: {actual!r} is not in {operand!r}")
        elif operator == "$prefix" and not (
            isinstance(actual, str)
            and isinstance(operand, str)
            and actual.startswith(operand)
        ):
            failures.append(f"{path}: {actual!r} lacks prefix {operand!r}")
        elif operator not in {"$eq", "$gte", "$lte", "$in", "$prefix"}:
            failures.append(f"{path}: unsupported assertion operator {operator}")
    return failures


def assertion_failures(expected: Any, actual: Any, path: str = "record") -> list[str]:
    if isinstance(expected, dict):
        if expected and all(str(key).startswith("$") for key in expected):
            return _operator_failures(expected, actual, path)
        if not isinstance(actual, dict):
            return [f"{path}: expected object, got {type(actual).__name__}"]
        failures: list[str] = []
        for key, child in expected.items():
            if key not in actual:
                failures.append(f"{path}.{key}: missing")
            else:
                failures.extend(assertion_failures(child, actual[key], f"{path}.{key}"))
        return failures
    if expected != actual:
        return [f"{path}: {actual!r} != {expected!r}"]
    return []


def masked_frame(frame: bytes, width: int, height: int,
                 masks: list[list[int]]) -> bytes:
    result = bytearray(frame)
    for mask in masks:
        if len(mask) != 4 or not all(isinstance(value, int) for value in mask):
            raise ValueError(f"invalid visual mask: {mask!r}")
        x, y, mask_width, mask_height = mask
        if (x < 0 or y < 0 or mask_width <= 0 or mask_height <= 0 or
                x + mask_width > width or y + mask_height > height):
            raise ValueError(f"out-of-bounds visual mask: {mask!r}")
        for row in range(y, y + mask_height):
            start = (row * width + x) * 2
            end = start + mask_width * 2
            result[start:end] = b"\0" * (end - start)
    return bytes(result)


def compare_or_record_golden(
    frame: bytes,
    width: int,
    height: int,
    capture: dict[str, Any],
    suite_path: Path,
    record_goldens: bool,
) -> dict[str, Any]:
    golden_path = (suite_path.parent / capture["golden"]).resolve()
    mode = capture.get("mode", "exact")
    masks = capture.get("masks", [])
    if not isinstance(masks, list):
        raise ValueError("visual masks must be a list")
    if not golden_path.exists():
        if not record_goldens:
            return {"status": "missing", "passed": False,
                    "golden": str(golden_path)}
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_bytes(zlib.compress(frame, level=9))
        return {"status": "recorded", "passed": True, "gate_eligible": False,
                "golden": str(golden_path), "source_sha256": sha256_bytes(frame)}
    if record_goldens:
        raise ValueError(f"refusing to overwrite existing golden: {golden_path}")
    golden = zlib.decompress(golden_path.read_bytes())
    expected_size = width * height * 2
    if len(golden) != expected_size:
        return {"status": "invalid_golden_size", "passed": False,
                "golden": str(golden_path), "bytes": len(golden),
                "expected_bytes": expected_size}
    compared_frame = masked_frame(frame, width, height, masks if mode == "masked_exact" else [])
    compared_golden = masked_frame(
        golden, width, height, masks if mode == "masked_exact" else []
    )
    mismatch_pixels = sum(
        compared_frame[offset:offset + 2] != compared_golden[offset:offset + 2]
        for offset in range(0, expected_size, 2)
    )
    return {
        "status": "matched" if mismatch_pixels == 0 else "mismatch",
        "passed": mismatch_pixels == 0,
        "golden": str(golden_path),
        "mode": mode,
        "masks": masks,
        "mismatch_pixels": mismatch_pixels,
        "actual_sha256": sha256_bytes(frame),
        "golden_sha256": sha256_bytes(golden),
    }


def diff_frame(actual: bytes, golden: bytes, width: int, height: int,
               masks: list[list[int]]) -> bytes:
    actual = masked_frame(actual, width, height, masks)
    golden = masked_frame(golden, width, height, masks)
    output = bytearray(len(actual))
    for offset in range(0, len(actual), 2):
        if actual[offset:offset + 2] != golden[offset:offset + 2]:
            output[offset:offset + 2] = b"\xF8\x00"  # RGB565 red
    return bytes(output)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def flash_candidate(port: str, firmware: Path, offset: int, baud: int) -> None:
    command = [
        sys.executable, "-m", "esptool", "--chip", "esp32s3", "--port", port,
        "--baud", str(baud), "write-flash", hex(offset), str(firmware),
    ]
    subprocess.run(command, check=True)


def capture_frame(device: Any) -> tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]:
    from capture_1x_ui import read_exact, read_json

    device.write(b"ui.capture\n")
    device.flush()
    begin = read_json(device, "leshy.ui.capture.v1", "frame_begin")
    if begin.get("format") != "rgb565be":
        raise RuntimeError(f"unsupported TFT format: {begin}")
    frame = read_exact(device, int(begin["bytes"]))
    end = read_json(device, "leshy.ui.capture.v1", "frame_end")
    device.write(b"ui.state\n")
    device.flush()
    state = read_json(device, "leshy.ui.v1", "state")
    if (begin.get("revision") != end.get("revision") or
            begin.get("revision") != state.get("revision")):
        raise RuntimeError("UI revision changed during TFT capture")
    return begin, frame, end, state


def action(device: Any, name: str) -> tuple[dict[str, Any], float]:
    from capture_1x_ui import read_json

    started = time.monotonic()
    device.write(f"ui.key {name}\n".encode("ascii"))
    device.flush()
    state = read_json(device, "leshy.ui.v1", "state")
    return state, round((time.monotonic() - started) * 1000.0, 3)


def query(device: Any, command: bytes, schema: str, kind: str) -> dict[str, Any]:
    from capture_1x_ui import read_json

    device.write(command + b"\n")
    device.flush()
    return read_json(device, schema, kind)


def run_device(args: argparse.Namespace, suite: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    import serial
    from capture_1x_boot import reset_and_capture
    from capture_1x_ui import PassiveSerial, rgb565be_to_png, synchronize_console

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    frames_dir = output / "frames"
    scenarios_dir = output / "scenarios"
    candidate_dir = output / "candidate"
    frames_dir.mkdir()
    scenarios_dir.mkdir()
    candidate_dir.mkdir()

    firmware_sha = sha256_file(args.firmware)
    firmware_app_elf_sha = app_elf_sha256(args.firmware)
    bundled_firmware = candidate_dir / "firmware.bin"
    shutil.copyfile(args.firmware, bundled_firmware)
    if (sha256_file(bundled_firmware) != firmware_sha or
            app_elf_sha256(bundled_firmware) != firmware_app_elf_sha):
        raise RuntimeError("bundled candidate identity changed during copy")
    run_id = secrets.token_hex(16)
    candidate = {
        "schema": "leshy.prerelease.candidate.v2",
        "firmware": "candidate/firmware.bin",
        "firmware_bytes": args.firmware.stat().st_size,
        "firmware_sha256": firmware_sha,
        "app_elf_sha256": firmware_app_elf_sha,
        "run_id": run_id,
        "flash_offset": args.flash_offset,
        "flashed_by_runner": args.flash,
        "suite_id": suite["id"],
        "suite_revision": suite["revision"],
    }
    write_json(output / "candidate-manifest.json", candidate)

    if args.flash:
        flash_candidate(args.port, bundled_firmware, args.flash_offset, args.flash_baud)

    with serial.Serial(args.port, 115200, timeout=0.05) as reset_device:
        raw_boot, first_byte_ms, ready_marker_ms = reset_and_capture(
            reset_device, args.boot_seconds
        )
    (output / "serial.ndjson").write_bytes(raw_boot)
    boot_records: list[dict[str, Any]] = []
    for line in raw_boot.splitlines():
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("schema") == "leshy.boot.v1":
            boot_records.append(value)
    ready = next((record for record in boot_records if record.get("kind") == "ready"), None)
    failures: list[str] = []
    if ready is None:
        failures.append("boot: missing leshy.boot.v1/ready")
        ready = {}
    failures.extend(assertion_failures(suite["boot_assert"], ready, "boot"))
    if ready.get("app_elf_sha256") != firmware_app_elf_sha:
        failures.append(
            "boot.app_elf_sha256: "
            f"{ready.get('app_elf_sha256')!r} != candidate {firmware_app_elf_sha!r}"
        )
    max_ready_ms = suite.get("maximum_ready_marker_ms")
    if not isinstance(ready_marker_ms, (int, float)):
        failures.append("boot: ready marker not observed")
    elif isinstance(max_ready_ms, (int, float)) and ready_marker_ms > max_ready_ms:
        failures.append(f"boot.ready_marker_ms: {ready_marker_ms:.3f} > {max_ready_ms}")

    trace: list[dict[str, Any]] = []
    gate_eligible = bool(args.flash) and not args.record_goldens
    device = PassiveSerial()
    device.port = args.port
    device.baudrate = 115200
    device.timeout = 0.25
    device.open()
    with device:
        synchronize_console(device)
        session_begin = query(
            device,
            f"hil.begin {run_id} {firmware_app_elf_sha}".encode("ascii"),
            "leshy.hil.session.v1", "begun",
        )
        failures.extend(assertion_failures({
            "status": "begun", "session_id": run_id, "active": True,
            "app_elf_sha256": firmware_app_elf_sha,
            "firmware_version": args.expected_version,
        }, session_begin, "hil_session.begin"))
        for scenario in suite["scenarios"]:
            scenario_trace: list[dict[str, Any]] = []
            for step in scenario["steps"]:
                if step.get("action") is None:
                    state = query(device, b"ui.state", "leshy.ui.v1", "state")
                    acknowledgement_ms = None
                else:
                    state, acknowledgement_ms = action(device, step["action"])
                step_failures = assertion_failures(
                    step["assert"], state, f"{scenario['id']}.{step['id']}"
                )
                failures.extend(step_failures)
                result: dict[str, Any] = {
                    "id": step["id"], "action": step.get("action"),
                    "acknowledgement_ms": acknowledgement_ms,
                    "state": state, "assertion_failures": step_failures,
                }
                capture = step.get("capture")
                if capture is not None:
                    begin, frame, end, post_state = capture_frame(device)
                    name = str(capture.get("name", step["id"]))
                    raw_path = frames_dir / f"{name}.rgb565"
                    png_path = frames_dir / f"{name}.png"
                    raw_path.write_bytes(frame)
                    png = rgb565be_to_png(frame, int(begin["width"]), int(begin["height"]))
                    png_path.write_bytes(png)
                    visual = compare_or_record_golden(
                        frame, int(begin["width"]), int(begin["height"]), capture,
                        args.suite.resolve(), args.record_goldens,
                    )
                    if visual.get("status") == "recorded":
                        gate_eligible = False
                    if not visual.get("passed", False):
                        failures.append(
                            f"{scenario['id']}.{step['id']}.visual: {visual.get('status')}"
                        )
                        golden_path = Path(str(visual.get("golden", "")))
                        if golden_path.exists():
                            golden = zlib.decompress(golden_path.read_bytes())
                            masks = capture.get("masks", []) if capture.get("mode") == "masked_exact" else []
                            diff = diff_frame(
                                frame, golden, int(begin["width"]), int(begin["height"]), masks
                            )
                            (frames_dir / f"{name}.diff.png").write_bytes(
                                rgb565be_to_png(diff, int(begin["width"]), int(begin["height"]))
                            )
                    result["capture"] = {
                        "name": name, "frame_begin": begin, "frame_end": end,
                        "post_state": post_state, "rgb565_sha256": sha256_bytes(frame),
                        "png_sha256": sha256_bytes(png), "visual": visual,
                    }
                    write_json(frames_dir / f"{name}.json", result["capture"])
                scenario_trace.append(result)
                trace.append({"scenario": scenario["id"], **result})
            write_json(scenarios_dir / f"{scenario['id']}.json", {
                "schema": "leshy.prerelease.scenario.v1",
                "id": scenario["id"], "steps": scenario_trace,
            })

        metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
        safe_outputs = query(
            device, b"hardware.safe-outputs",
            "leshy.hardware.safe-outputs.v1", "state",
        )
        final_state = query(device, b"ui.state", "leshy.ui.v1", "state")
        session_end = query(
            device, f"hil.end {run_id}".encode("ascii"),
            "leshy.hil.session.v1", "ended",
        )
        failures.extend(assertion_failures({
            "status": "ended", "session_id": run_id, "active": False,
            "app_elf_sha256": firmware_app_elf_sha,
        }, session_end, "hil_session.end"))

    failures.extend(assertion_failures(
        suite.get("final_state_assert", {}), final_state, "final_state"
    ))
    failures.extend(assertion_failures(
        suite.get("metrics_assert", {}), metrics, "metrics"
    ))
    failures.extend(assertion_failures(
        suite.get("safe_outputs_assert", {}), safe_outputs, "safe_outputs"
    ))
    if metrics.get("app_elf_sha256") != firmware_app_elf_sha:
        failures.append(
            "metrics.app_elf_sha256: "
            f"{metrics.get('app_elf_sha256')!r} != candidate {firmware_app_elf_sha!r}"
        )
    result = {
        "schema": RUN_SCHEMA,
        "suite_id": suite["id"], "suite_revision": suite["revision"],
        "candidate_sha256": firmware_sha,
        "candidate_app_elf_sha256": firmware_app_elf_sha,
        "run_id": run_id,
        "candidate_flashed": args.flash,
        "expected_version": args.expected_version,
        "boot": {"first_byte_ms": first_byte_ms, "ready_marker_ms": ready_marker_ms,
                 "ready": ready},
        "metrics": metrics, "safe_outputs": safe_outputs,
        "hil_session": {"begin": session_begin, "end": session_end},
        "final_state": final_state, "trace": trace,
        "goldens_recorded": args.record_goldens,
        "gate_eligible": gate_eligible and not failures,
        "passed": not failures,
        "failures": failures,
    }
    if ready.get("version") != args.expected_version:
        failure = f"boot.version: {ready.get('version')!r} != {args.expected_version!r}"
        failures.append(failure)
        result["passed"] = False
        result["gate_eligible"] = False
        result["failures"] = failures
    return result, failures


def finalize_bundle(output: Path, result: dict[str, Any]) -> None:
    write_json(output / "run.json", result)
    artifact_lines: list[str] = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name not in {
            "artifacts.sha256", "runner-result.json"
        }:
            artifact_lines.append(f"{sha256_file(path)}  {path.relative_to(output)}")
    payload = "\n".join(artifact_lines) + "\n"
    (output / "artifacts.sha256").write_text(payload, encoding="utf-8")
    runner_result: dict[str, Any] = {
        "schema": "leshy.prerelease.runner_result.v1",
        "candidate_sha256": result.get("candidate_sha256"),
        "app_elf_sha256": result.get("candidate_app_elf_sha256"),
        "run_id": result.get("run_id"),
        "suite_id": result.get("suite_id"),
        "suite_revision": result.get("suite_revision"),
        "passed": result.get("passed", False),
        "gate_eligible": False,
        "bundle_sha256": sha256_bytes(payload.encode("utf-8")),
        "trust_status": "unsigned_local_result",
        "reason": (
            "release trust is established by GitHub Artifact Attestations over "
            "the packaged evidence bundle"
        ),
    }
    write_json(output / "runner-result.json", runner_result)


def parse_offset(value: str) -> int:
    parsed = int(value, 0)
    if parsed < 0 or parsed > 0xFFFFFF:
        raise argparse.ArgumentTypeError("flash offset is out of range")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true",
                        help="flash the exact candidate before the cold-boot suite")
    parser.add_argument("--flash-offset", type=parse_offset, default=0x10000)
    parser.add_argument("--flash-baud", type=int, default=460800)
    parser.add_argument("--boot-seconds", type=float, default=5.0)
    parser.add_argument("--record-goldens", action="store_true",
                        help="create missing goldens; refuses to overwrite existing ones")
    args = parser.parse_args()
    if not args.firmware.is_file():
        parser.error(f"firmware not found: {args.firmware}")
    if args.output.exists():
        parser.error(f"output must not exist: {args.output}")
    if args.record_goldens and not args.flash:
        parser.error("--record-goldens requires --flash")

    suite = load_suite(args.suite)
    try:
        result, failures = run_device(args, suite)
    except Exception as error:  # Preserve a machine-readable failed bundle.
        args.output.mkdir(parents=True, exist_ok=True)
        result = {
            "schema": RUN_SCHEMA, "suite_id": suite["id"],
            "suite_revision": suite["revision"], "passed": False,
            "gate_eligible": False, "failures": [f"runner: {type(error).__name__}: {error}"],
        }
        failures = result["failures"]
    finalize_bundle(args.output.resolve(), result)
    print(json.dumps({
        "output": str(args.output.resolve()), "passed": result.get("passed", False),
        "gate_eligible": result.get("gate_eligible", False),
        "failures": failures,
    }, sort_keys=True))
    return 0 if result.get("passed", False) else 2


if __name__ == "__main__":
    raise SystemExit(main())
