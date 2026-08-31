#!/usr/bin/env python3
"""One-flash focused HIL for passive Wi-Fi/BLE Targets Radar."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    capture,
    query,
)
from run_1x_ui_typography_hil import normalize_home
from temporary_device_lock_hil import TemporaryProtectedUiAdmissionHil


SCHEMA = "leshy.targets_radar_hil.run.v1"
RADAR_SCHEMA = "leshy.targets.radar.v1"
TARGETS_SCHEMA = "leshy.targets.product.v1"
RADAR_HIL_OBSERVATION_SCHEMA = "leshy.targets.radar_hil_observation.v1"
CID = "FE343253440000002000000055019CB7"
RADIO_NAMES = {1: "wifi", 2: "ble"}


def require(record: dict[str, Any], label: str, **expected: Any) -> None:
    actual = {key: record.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(f"{label}: expected={expected}, actual={actual}")


def wait_record(device: PassiveSerial, command: bytes, schema: str,
                predicate: Any, timeout: float, description: str
                ) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = query(device, command, schema, "state")
        if predicate(last):
            return last
        time.sleep(0.05)
    raise TimeoutError(f"{description}: last state {last!r}")


def wait_live_or_healthy(device: PassiveSerial, radio: str,
                         timeout: float) -> tuple[dict[str, Any], bool]:
    """Prefer an exact live match, but retain a proven healthy no-match.

    A persisted target can legitimately be out of range during a release run.
    That must not be confused with a failed receiver lifecycle: the physical
    scanner still has to complete two valid passive cycles with clean teardown
    telemetry. At least one selected radio is required to produce a live match
    later in the run so atomic on-device delta rendering remains HIL-proven.
    """
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    healthy: dict[str, Any] = {}
    scan_key = "ble_scans" if radio == "ble" else "wifi_scans"
    while time.monotonic() < deadline:
        last = query(device, b"targets.radar", RADAR_SCHEMA, "state")
        active = (
            last.get("overlay_open") is True and
            last.get("worker_control") == "running" and
            last.get("passive_only") is True and
            last.get("cleanup_complete") is True
        )
        source_healthy = active and int(last.get("cycles", 0)) >= 1
        if radio == "ble":
            source_healthy = (
                source_healthy and
                last.get("ble_begin_stage") in {"ready", "reused_ready"} and
                int(last.get("ble_begin_error", -1)) == 0 and
                last.get("ble_scan_status") == "valid" and
                int(last.get("ble_scan_attempts", 0)) >= 1 and
                int(last.get("ble_records_dropped", -1)) == 0 and
                last.get("ble_cleanup_complete") is True
            )
        if source_healthy:
            healthy = last
        matched = (
            source_healthy and last.get("signal_radio") == radio and
            int(last.get("samples", 0)) >= 1 and
            int(last.get("rendered_revision", 0)) ==
                int(last.get("revision", -1))
        )
        if matched:
            return last, True
        if healthy and int(last.get(scan_key, 0)) >= 2:
            return healthy, False
        if last.get("worker_control") == "idle":
            raise RuntimeError(
                f"{radio} Radar source stopped before a healthy cycle: {last!r}")
        time.sleep(0.05)
    if healthy:
        return healthy, False
    raise TimeoutError(
        f"{radio} Radar did not complete a healthy passive cycle: {last!r}")


def pixel_regions(frames: Path, before: str, after: str) -> dict[str, int]:
    first = (frames / f"{before}.rgb565").read_bytes()
    second = (frames / f"{after}.rgb565").read_bytes()
    if len(first) != 240 * 320 * 2 or len(second) != len(first):
        raise RuntimeError("complete 240x320 RGB565 frames required")
    identity = 0
    live = 0
    chrome = 0
    for y in range(320):
        for x in range(240):
            offset = (y * 240 + x) * 2
            if first[offset:offset + 2] == second[offset:offset + 2]:
                continue
            if 12 <= x < 228 and 82 <= y < 293:
                live += 1
            elif 12 <= x < 228 and 32 <= y < 82:
                identity += 1
            else:
                chrome += 1
    return {
        "identity_changed_pixels": identity,
        "live_changed_pixels": live,
        "chrome_changed_pixels": chrome,
    }


def open_targets(device: PassiveSerial,
                 trace: list[dict[str, Any]]) -> dict[str, Any]:
    state = normalize_home(device)
    for _ in range(5):
        state = action(device, "down")
        trace.append(state)
    require(state, "Targets selected", page="home", selection=5,
            selected_id="targets")
    opened = action(device, "right")
    trace.append(opened)
    require(opened, "Targets opened", page="targets",
            runtime_owner="targets", lease_mask=13)
    state = query(device, b"targets.state", TARGETS_SCHEMA, "state")
    require(state, "Targets ready", status="ready", view="list",
            page_open=True, workspace_allocated=True,
            blocked_write_attempts=0, lease_mask=13)
    if int(state.get("target_count", 0)) < 1:
        raise RuntimeError(f"Targets catalog is empty: {state!r}")
    return state


def run_selected_radar(device: PassiveSerial, frames: Path, radio: str,
                       trace: list[dict[str, Any]],
                       screens: dict[str, Any], *, case_name: str | None = None,
                       heap_tolerance: int = 512) -> dict[str, Any]:
    detail = query(device, b"targets.state", TARGETS_SCHEMA, "state")
    require(detail, f"{radio} detail", view="detail",
            selected_target_present=True, blocked_write_attempts=0)
    graph = str(detail.get("selected_graph_fingerprint", ""))
    target_id = str(detail.get("selected_target_id", ""))
    identity_hex = str(detail.get("selected_observation_identity_hex", ""))
    identity_radio = int(detail.get("selected_observation_radio", 0))
    if len(graph) != 16 or len(target_id) != 32 or \
            len(identity_hex) != 12 or \
            RADIO_NAMES.get(identity_radio) != radio:
        raise RuntimeError(f"{radio} target identity is incomplete: {detail!r}")
    heap_before = int(query(
        device, b"metrics", "leshy.boot.v1", "ready")["heap_free"])

    actions = action(device, "right")
    trace.append(actions)
    actions_state = query(device, b"targets.state", TARGETS_SCHEMA, "state")
    require(actions_state, f"{radio} actions", view="actions",
            action_selection=0)
    started = action(device, "right")
    trace.append(started)
    require(started, f"{radio} radar open", page="targets",
            runtime_owner="targets", lease_mask=15)
    first, physical_live_match = wait_live_or_healthy(device, radio, 25.0)
    require(first, f"{radio} first radar", task_active=True,
            cleanup_complete=True, passive_only=True,
            blocked_write_attempts=0, physical_write_calls=0,
            identity_disclosed=False, lease_mask=15)
    injections: list[dict[str, Any]] = []
    if not physical_live_match:
        injected = query(
            device, f"targets.radar.hil-observe {radio} -72".encode("ascii"),
            RADAR_HIL_OBSERVATION_SCHEMA, "observation")
        require(injected, f"{radio} deterministic observation",
                status="injected", radio=radio, rssi_dbm=-72,
                injected=True, hil_active=True, overlay_open=True,
                passive_receiver_untouched=True, radio_tx_commands=0,
                storage_writes=0, identity_disclosed=False)
        injections.append(injected)
        first = wait_record(
            device, b"targets.radar", RADAR_SCHEMA,
            lambda value: (
                value.get("overlay_open") is True and
                value.get("worker_control") == "running" and
                value.get("signal_radio") == radio and
                int(value.get("samples", 0)) >= 1 and
                int(value.get("rendered_revision", 0)) ==
                    int(value.get("revision", -1))
            ), 5.0, f"{radio} injected target was not rendered")
    live_match = physical_live_match or bool(injections)
    name = case_name or radio
    first_name = f"target-radar-{name}-first"
    screens[first_name] = capture(device, frames, first_name)
    second: dict[str, Any] | None = None
    pixels: dict[str, int] | None = None
    if live_match:
        if injections:
            injected = query(
                device,
                f"targets.radar.hil-observe {radio} -54".encode("ascii"),
                RADAR_HIL_OBSERVATION_SCHEMA, "observation")
            require(injected, f"{radio} deterministic delta",
                    status="injected", radio=radio, rssi_dbm=-54,
                    injected=True, hil_active=True, overlay_open=True,
                    passive_receiver_untouched=True, radio_tx_commands=0,
                    storage_writes=0, identity_disclosed=False)
            injections.append(injected)
        second = wait_record(
            device, b"targets.radar", RADAR_SCHEMA,
            lambda value: (
                value.get("overlay_open") is True and
                value.get("worker_control") == "running" and
                value.get("signal_radio") == radio and
                int(value.get("samples", 0)) > int(first["samples"]) and
                int(value.get("rendered_revision", 0)) ==
                    int(value.get("revision", -1)) and
                int(value.get("delta_repaints", 0)) >
                    int(first["delta_repaints"])
            ),
            25.0, f"{radio} target radar did not update atomically")
        if int(second["full_repaints"]) != int(first["full_repaints"]) or \
                int(second["content_clears"]) != \
                    int(first["content_clears"]):
            raise RuntimeError(f"{radio} live update performed a full repaint")
        second_name = f"target-radar-{name}-second"
        screens[second_name] = capture(device, frames, second_name)
        pixels = pixel_regions(frames, first_name, second_name)
        if pixels["identity_changed_pixels"] != 0 or \
                pixels["chrome_changed_pixels"] != 0 or \
                pixels["live_changed_pixels"] == 0:
            raise RuntimeError(
                f"{radio} redraw escaped live region: {pixels}")

    stopping = action(device, "back")
    trace.append(stopping)
    try:
        restored = wait_record(
            device, b"targets.state", TARGETS_SCHEMA,
            lambda value: value.get("view") == "actions" and
                value.get("selected_observation_identity_hex") ==
                    identity_hex and
                int(value.get("selected_observation_radio", 0)) ==
                    identity_radio,
            15.0, f"{radio} target was not restored after Radar")
    except Exception as error:
        radar_failure = query(
            device, b"targets.radar", RADAR_SCHEMA, "state")
        raise RuntimeError(
            f"{error}; radar restore diagnostics={radar_failure!r}") from error
    require(restored, f"{radio} restored", status="ready",
            workspace_allocated=True, page_open=True, view="actions",
            action_selection=0, blocked_write_attempts=0, lease_mask=13)
    radar_after = query(device, b"targets.radar", RADAR_SCHEMA, "state")
    require(radar_after, f"{radio} radar cleanup", status="idle",
            overlay_open=False, worker_control="idle", task_active=False,
            worker_finished=False, cleanup_complete=True, passive_only=True,
            blocked_write_attempts=0, physical_write_calls=0,
            identity_disclosed=False, lease_mask=13)
    if radar_after.get("restore_match") not in {
            "target_id", "radio_identity"}:
        raise RuntimeError(
            f"{radio} Radar did not report an exact restore match: "
            f"{radar_after!r}")
    heap_after = int(query(
        device, b"metrics", "leshy.boot.v1", "ready")["heap_free"])
    if heap_after + heap_tolerance < heap_before:
        raise RuntimeError(
            f"{radio} Radar leaked heap: {heap_before}->{heap_after}")
    return {
        "radio": radio,
        "selected_target_id": target_id,
        "selected_graph_fingerprint": graph,
        "selected_identity_hex": identity_hex,
        "selected_identity_radio": identity_radio,
        "restored_target_id": restored.get("selected_target_id"),
        "restored_graph_fingerprint":
            restored.get("selected_graph_fingerprint"),
        "restore_match": radar_after.get("restore_match"),
        "target_id_stable":
            restored.get("selected_target_id") == target_id,
        "source_lifecycle_proven": True,
        "live_match": live_match,
        "physical_live_match": physical_live_match,
        "hil_observation_injected": bool(injections),
        "hil_observations": injections,
        "first": first,
        "second": second,
        "after": radar_after,
        "restored": restored,
        "heap_free_before": heap_before,
        "heap_free_after": heap_after,
        "heap_tolerance": heap_tolerance,
        "pixel_changes": pixels,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--reuse-exact-flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()
    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one of --flash or --reuse-exact-flash")
    for path in (args.firmware, args.elf, args.map):
        if not path.is_file():
            parser.error(f"candidate artifact missing: {path}")
    if args.output.exists():
        parser.error("output must not exist")
    if len(args.source_commit) != 40:
        parser.error("source commit must be full length")
    root = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", args.source_commit, head],
        cwd=root, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL).returncode == 0
    if status or not ancestor:
        parser.error("HIL requires a clean harness descended from source commit")

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    shutil.copyfile(args.firmware, candidate)
    app_identity = app_elf_sha256(candidate)
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "in_progress",
        "candidate": {
            "version": args.expected_version,
            "source_commit": args.source_commit,
            "harness_commit": head,
            "firmware_sha256": sha256_file(candidate),
            "elf_sha256": sha256_file(args.elf),
            "map_sha256": sha256_file(args.map),
            "app_elf_sha256": app_identity,
            "flash_mode": "flash" if args.flash else "reuse_exact",
        },
        "expected_cid": CID,
    }
    write_json(args.output / "run.json", record)
    trace: list[dict[str, Any]] = []
    screens: dict[str, Any] = {}
    lifecycles: list[dict[str, Any]] = []
    cleanup: dict[str, Any] = {"attempted": False}
    admission: TemporaryProtectedUiAdmissionHil | None = None
    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.25) as device:
            synchronize_console(device, 30.0)
            metrics = query(device, b"metrics", "leshy.boot.v1", "ready")
            require(metrics, "candidate", version=args.expected_version,
                    app_elf_sha256=app_identity)
            recovery_before = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            require(recovery_before, "product media", status="admitted",
                    expected_fingerprint=CID, observed_fingerprint=CID,
                    fingerprint_matched=True, mounted_read_only=True,
                    read_only_guaranteed=True, blocked_write_attempts=0,
                    physical_write_calls=0, cleanup_complete=True)
            admission = TemporaryProtectedUiAdmissionHil(device, app_identity)
            admission.start()
            targets = open_targets(device, trace)

            wanted = {"wifi", "ble"}
            rows = int(targets["target_count"])
            for _ in range(rows):
                selected = action(device, "down")
                trace.append(selected)
                opened = action(device, "select")
                trace.append(opened)
                detail = query(device, b"targets.state", TARGETS_SCHEMA,
                               "state")
                radio = RADIO_NAMES.get(
                    int(detail.get("selected_observation_radio", 0)))
                if radio in wanted:
                    lifecycle = run_selected_radar(
                        device, frames, radio, trace, screens,
                        heap_tolerance=2048)
                    lifecycles.append(lifecycle)
                    # Both ESP-IDF radio stacks may retain a small first-use
                    # cache. Repeat the exact lifecycle without a second flash:
                    # only a stable second result proves bounded warm-up rather
                    # than a repeatable leak.
                    detail_again = action(device, "back")
                    trace.append(detail_again)
                    require(detail_again, f"{radio} warm detail",
                            page="targets", runtime_owner="targets",
                            lease_mask=13)
                    repeat = run_selected_radar(
                        device, frames, radio, trace, screens,
                        case_name=f"{radio}-repeat", heap_tolerance=512)
                    lifecycles.append(repeat)
                    if repeat["heap_free_after"] + 512 < \
                            lifecycle["heap_free_after"]:
                        raise RuntimeError(
                            f"{radio} Radar heap declined across clean repeats: "
                            f"{lifecycle['heap_free_after']}->"
                            f"{repeat['heap_free_after']}")
                    wanted.remove(radio)
                    # Radar restores the exact Actions view. Return through
                    # Detail to List before selecting the next stable row.
                    trace.append(action(device, "back"))
                    trace.append(action(device, "back"))
                else:
                    trace.append(action(device, "back"))
                if not wanted:
                    break
            if wanted:
                raise RuntimeError(
                    f"persisted Targets pair has no live candidates for {wanted}")
            if not all(item["live_match"] for item in lifecycles):
                raise RuntimeError("Radar atomic live delta remains unproven")

            home = action(device, "back")
            trace.append(home)
            require(home, "Targets final cleanup", page="home",
                    runtime_owner="none", lease_mask=0,
                    survey_product_worker_ready=True)
            admission.close()
            hil_observation_negative = query(
                device, b"targets.radar.hil-observe wifi -40",
                RADAR_HIL_OBSERVATION_SCHEMA, "observation")
            require(
                hil_observation_negative, "closed HIL observation fixture",
                status="hil_session_required", radio="wifi", rssi_dbm=-40,
                injected=False, hil_active=False, overlay_open=False,
                passive_receiver_untouched=True, radio_tx_commands=0,
                storage_writes=0, identity_disclosed=False)
            recovery_after = query(
                device, b"storage.product.boot-recovery",
                "leshy.storage.product_boot_recovery.v1", "state")
            require(recovery_after, "unchanged media", status="admitted",
                    generation=recovery_before["generation"],
                    observations=recovery_before["observations"],
                    blocked_write_attempts=0, physical_write_calls=0,
                    cleanup_complete=True)
            inputs = query(device, b"input.state",
                           "leshy.input.frontend.v1", "state")
            require(inputs, "input", status="ready", read_errors=0,
                    queue_drops=0)
            safe = query(device, b"hardware.safe-outputs",
                         "leshy.hardware.safe-outputs.v1", "state")
            require(safe, "safe outputs", buzzer_inactive=True,
                    nrf_ce_inactive=True, software_quiesce_complete=True)
            cleanup = best_effort_cleanup(device)
            if not cleanup.get("complete"):
                raise RuntimeError("terminal cleanup is not proven")
            require(cleanup.get("final_state", {}),
                    "terminal Survey worker", page="home",
                    runtime_owner="none", lease_mask=0,
                    survey_product_worker_ready=True)

        record.update({
            "status": "pass",
            "passed": True,
            "gate_eligible": True,
            "failures": [],
            "recovery_before": recovery_before,
            "recovery_after": recovery_after,
            "lifecycles": lifecycles,
            "screens": screens,
            "input": inputs,
            "safe_outputs": safe,
            "device_lock_fixture": admission.evidence(),
            "cleanup": cleanup,
            "trace": trace,
            "flash_count": 1 if args.flash else 0,
            "radio_tx_commands": 0,
            "active_probe_commands": 0,
            "deterministic_observation_injections": sum(
                len(item["hil_observations"]) for item in lifecycles),
            "hil_observation_negative": hil_observation_negative,
            "ambient_frames_retained_by_firmware": False,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(json.dumps({"schema": SCHEMA, "status": "pass",
                          "run": str(args.output / "run.json"),
                          "radios": [item["radio"] for item in lifecycles]},
                         sort_keys=True))
        return 0
    except Exception as error:
        try:
            with PassiveSerial(args.port, 115200, timeout=0.25) as device:
                synchronize_console(device, 10.0)
                if admission is not None:
                    admission.rebind(device)
                    admission.close()
                cleanup = best_effort_cleanup(device)
        except Exception as cleanup_error:
            cleanup = {"attempted": True, "complete": False,
                       "errors": [f"{type(cleanup_error).__name__}: "
                                  f"{cleanup_error}"]}
        record.update({"status": "failed", "passed": False,
                       "gate_eligible": False, "failures": [str(error)],
                       "lifecycles": lifecycles, "screens": screens,
                       "trace": trace, "cleanup": cleanup,
                       "device_lock_fixture": None if admission is None
                       else admission.evidence()})
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
