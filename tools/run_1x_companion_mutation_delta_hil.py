#!/usr/bin/env python3
"""Focused one-flash HIL for confirmed S6.5 companion Target mutations."""

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
from run_1x_companion_usb_delta_hil import (
    collect_pages,
    companion_request,
    connect,
    request,
)
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    query,
    reset_capture,
)
from run_1x_ui_typography_hil import normalize_home


SCHEMA = "leshy.companion_mutation_delta_hil.run.v1"
PROTOCOL_SCHEMA = "leshy.companion.response.v1"
EXPECTED_CID = "FE343253440000002000000055019CB7"
MUTATION_SCOPES = ["target.read", "target.mutate"]
MUTATION_CAPABILITIES = [
    "target.list",
    "target.detail",
    "target.favorite.set",
    "target.name.set",
    "target.notes.set",
    "target.tag.add",
    "target.tag.remove",
]


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def checkpoint(path: Path, record: dict[str, Any], name: str) -> None:
    record["checkpoint"] = name
    write_json(path / "run.json", record)


def open_targets(device: PassiveSerial) -> dict[str, Any]:
    home = normalize_home(device)
    for _ in range(5):
        home = action(device, "down")
    require(home.get("page") == "home" and
            home.get("selection") == 5 and
            home.get("selected_id") == "targets",
            f"cannot focus Targets: {home}")
    opened = action(device, "right")
    require(opened.get("page") == "targets" and
            opened.get("runtime_owner") == "targets" and
            opened.get("lease_mask") == 13,
            f"cannot open Targets: {opened}")
    state = query(device, b"targets.state",
                  "leshy.targets.product.v1", "state")
    require(state.get("status") == "ready" and
            state.get("workspace_allocated") is True and
            state.get("cleanup_complete") is True and
            state.get("blocked_write_attempts") == 0,
            f"Targets snapshot unavailable: {state}")
    return state


def target_by_id(device: PassiveSerial, target_id: str | None = None) \
        -> tuple[dict[str, Any], list[dict[str, Any]]]:
    targets, pages = collect_pages(device, "target.list", "target-list", {})
    require(bool(targets), "target.list returned no Targets")
    if target_id is None:
        return targets[0], pages
    for target in targets:
        if target.get("target_id") == target_id:
            return target, pages
    raise RuntimeError(f"Target {target_id} disappeared from companion list")


def favorite_preview(device: PassiveSerial, request_id: str,
                     target: dict[str, Any], favorite: bool,
                     revision: int | None = None) -> dict[str, Any]:
    return companion_request(device, request(
        "target.mutation.preview", request_id,
        action="target.favorite.set",
        target_id=target["target_id"],
        expected_revision=(target["revision"] if revision is None else revision),
        favorite=favorite))


def confirm(device: PassiveSerial, request_id: str,
            mutation_id: str) -> dict[str, Any]:
    return companion_request(device, request(
        "target.mutation.confirm", request_id, mutation_id=mutation_id))


def wait_mutation(device: PassiveSerial, mutation_id: str,
                  timeout: float = 20.0) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout
    samples: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        response = companion_request(device, request(
            "target.mutation.status", f"status-{len(samples)}",
            mutation_id=mutation_id))
        samples.append(response)
        if response.get("state") in ("saved", "failed"):
            return response, samples
        time.sleep(0.05)
    raise TimeoutError(f"companion mutation did not finish: {samples[-4:]}")


def assert_atomic_report(state: dict[str, Any], expected_generation: int) -> None:
    require(state.get("status") == "ready" and
            state.get("mutation_state") == "saved" and
            state.get("mutation_status") == "saved" and
            state.get("mutation_persisted") is True and
            state.get("mutation_generation") == expected_generation and
            state.get("target_state_generation") == expected_generation and
            state.get("mutation_expected_cid") == EXPECTED_CID and
            state.get("mutation_observed_cid") == EXPECTED_CID and
            state.get("mutation_write_calls") == 3 and
            state.get("mutation_file_syncs") == 3 and
            state.get("mutation_directory_syncs") == 3 and
            state.get("cleanup_complete") is True and
            state.get("lease_mask") == 13,
            f"atomic companion save invariant failed: {state}")
    attempts = int(state.get("mutation_identity_attempts", 0))
    retries = int(state.get("mutation_identity_transient_retries", -1))
    require(1 <= attempts <= 8 and retries == attempts - 1,
            f"identity retry accounting invalid: {state}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()

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
    if head != args.source_commit or status:
        parser.error("exact HIL requires clean committed HEAD")

    args.output.mkdir(parents=True)
    candidate = args.output / "firmware.bin"
    retained_elf = args.output / "firmware.elf"
    retained_map = args.output / "firmware.map"
    shutil.copyfile(args.firmware, candidate)
    shutil.copyfile(args.elf, retained_elf)
    shutil.copyfile(args.map, retained_map)
    app_identity = app_elf_sha256(candidate)
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "in_progress",
        "source_commit": args.source_commit,
        "harness_commit": head,
        "target": {
            "port": args.port,
            "serial_port_discovery_calls": 0,
            "ports_opened": [args.port],
            "cardputer_ports_opened": 0,
        },
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": sha256_file(candidate),
            "firmware_bytes": candidate.stat().st_size,
            "elf_sha256": sha256_file(retained_elf),
            "map_sha256": sha256_file(retained_map),
            "app_elf_sha256": app_identity,
        },
        "flash_count": 0,
    }
    write_json(args.output / "run.json", record)
    cleanup: dict[str, Any] = {"attempted": False}
    device: PassiveSerial | None = None

    try:
        checkpoint(args.output, record, "flash_original_div")
        flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
        record["flash_count"] = 1
        write_json(args.output / "run.json", record)
        time.sleep(1.0)
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 30.0)
        metrics_before = query(device, b"metrics", "leshy.boot.v1", "ready")
        require(metrics_before.get("version") == args.expected_version and
                metrics_before.get("app_elf_sha256") == app_identity,
                f"wrong candidate booted: {metrics_before}")
        recovery = query(device, b"storage.product.boot-recovery",
                         "leshy.storage.product_boot_recovery.v1", "state")
        require(recovery.get("status") == "admitted" and
                recovery.get("expected_fingerprint") == EXPECTED_CID and
                recovery.get("observed_fingerprint") == EXPECTED_CID and
                recovery.get("fingerprint_matched") is True and
                recovery.get("mounted_read_only") is True and
                recovery.get("read_only_guaranteed") is True and
                recovery.get("blocked_write_attempts") == 0 and
                recovery.get("physical_write_calls") == 0,
                f"exact product media unavailable: {recovery}")

        checkpoint(args.output, record, "home_denial")
        home_denied = connect(device, "home-mutation", MUTATION_SCOPES)
        require(home_denied.get("status") == "denied" and
                home_denied.get("reason") == "scope_unavailable",
                f"Home exposed mutation scope: {home_denied}")

        checkpoint(args.output, record, "open_targets_connect")
        state_before = open_targets(device)
        generation_before = int(state_before["target_state_generation"])
        ready = connect(device, "mutation-connect", MUTATION_SCOPES)
        require(ready.get("status") == "ready" and
                ready.get("reason") == "none" and
                ready.get("scopes") == MUTATION_SCOPES and
                ready.get("capabilities") == MUTATION_CAPABILITIES and
                ready.get("max_frame_bytes") == 512,
                f"mutation connection not granted exactly: {ready}")
        target_before, list_before = target_by_id(device)
        target_id = str(target_before["target_id"])
        revision_before = int(target_before["revision"])
        favorite_before = bool(target_before["favorite"])

        checkpoint(args.output, record, "negative_preview_confirm")
        no_op = favorite_preview(
            device, "no-op", target_before, favorite_before)
        require(no_op.get("status") == "error" and
                no_op.get("reason") == "unchanged" and
                "mutation_id" not in no_op,
                f"no-op preview was admitted: {no_op}")
        stale = favorite_preview(
            device, "stale", target_before, not favorite_before,
            revision_before + 1)
        require(stale.get("status") == "error" and
                stale.get("reason") == "revision_conflict" and
                stale.get("target_revision") == revision_before,
                f"stale preview was admitted: {stale}")
        unknown_id = "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
        unknown_confirm = confirm(device, "unknown", unknown_id)
        require(unknown_confirm.get("status") == "error" and
                unknown_confirm.get("reason") == "unknown_mutation",
                f"unknown confirm was admitted: {unknown_confirm}")

        checkpoint(args.output, record, "first_preview_confirm")
        first_preview = favorite_preview(
            device, "first-preview", target_before, not favorite_before)
        mutation_id = first_preview.get("mutation_id")
        require(first_preview.get("status") == "ok" and
                first_preview.get("state") == "previewed" and
                isinstance(mutation_id, str) and len(mutation_id) == 32 and
                first_preview.get("expected_revision") == revision_before and
                first_preview.get("target_revision") == revision_before + 1,
                f"valid preview failed: {first_preview}")
        wrong_confirm = confirm(device, "wrong-token", unknown_id)
        require(wrong_confirm.get("reason") == "unknown_mutation",
                f"changed token was accepted: {wrong_confirm}")
        first_confirm = confirm(device, "first-confirm", mutation_id)
        require(first_confirm.get("status") == "ok" and
                first_confirm.get("state") == "saving",
                f"confirmed mutation was not queued: {first_confirm}")
        replay_confirm = confirm(device, "first-replay", mutation_id)
        require(replay_confirm.get("status") == "error" and
                replay_confirm.get("reason") == "already_confirmed",
                f"one-time confirmation replay succeeded: {replay_confirm}")
        first_terminal, first_status_samples = wait_mutation(
            device, mutation_id)
        require(first_terminal.get("status") == "ok" and
                first_terminal.get("state") == "saved" and
                first_terminal.get("target_revision") == revision_before + 1 and
                first_terminal.get("state_generation") == generation_before + 1,
                f"first mutation failed: {first_terminal}")
        first_state = query(device, b"targets.state",
                            "leshy.targets.product.v1", "state")
        assert_atomic_report(first_state, generation_before + 1)
        target_after, list_after = target_by_id(device, target_id)
        require(target_after.get("revision") == revision_before + 1 and
                target_after.get("favorite") is (not favorite_before),
                f"first value did not reopen in companion: {target_after}")

        checkpoint(args.output, record, "restore_preview_confirm")
        second_preview = favorite_preview(
            device, "restore-preview", target_after, favorite_before)
        restore_id = second_preview.get("mutation_id")
        require(second_preview.get("status") == "ok" and
                second_preview.get("state") == "previewed" and
                isinstance(restore_id, str) and len(restore_id) == 32,
                f"restore preview failed: {second_preview}")
        second_confirm = confirm(device, "restore-confirm", restore_id)
        require(second_confirm.get("status") == "ok" and
                second_confirm.get("state") == "saving",
                f"restore mutation was not queued: {second_confirm}")
        second_terminal, second_status_samples = wait_mutation(
            device, restore_id)
        require(second_terminal.get("status") == "ok" and
                second_terminal.get("state") == "saved" and
                second_terminal.get("target_revision") == revision_before + 2 and
                second_terminal.get("state_generation") == generation_before + 2,
                f"restore mutation failed: {second_terminal}")
        second_state = query(device, b"targets.state",
                             "leshy.targets.product.v1", "state")
        assert_atomic_report(second_state, generation_before + 2)
        target_restored, list_restored = target_by_id(device, target_id)
        require(target_restored.get("revision") == revision_before + 2 and
                target_restored.get("favorite") is favorite_before,
                f"favorite was not restored: {target_restored}")

        checkpoint(args.output, record, "grant_revoke_and_cold_reopen")
        exited = action(device, "left")
        require(exited.get("page") == "home" and
                exited.get("runtime_owner") == "none" and
                exited.get("lease_mask") == 0,
                f"Targets did not release: {exited}")
        revoked = companion_request(device, request(
            "target.mutation.status", "revoked", mutation_id=restore_id))
        require(revoked.get("reason") in ("not_connected", "unknown_mutation"),
                f"grant/pending mutation survived Targets exit: {revoked}")
        device.close()
        device = None

        ready_after, _, reset_timing = reset_capture(
            args.port, args.output, "companion-mutation-cold-reopen", 20.0)
        require(ready_after.get("version") == args.expected_version and
                ready_after.get("app_elf_sha256") == app_identity,
                f"cold reset booted wrong candidate: {ready_after}")
        device = PassiveSerial(args.port, 115200, timeout=0.25)
        synchronize_console(device, 20.0)
        recovery_after = query(
            device, b"storage.product.boot-recovery",
            "leshy.storage.product_boot_recovery.v1", "state")
        require(recovery_after.get("status") == "admitted" and
                recovery_after.get("expected_fingerprint") == EXPECTED_CID and
                recovery_after.get("observed_fingerprint") == EXPECTED_CID and
                recovery_after.get("physical_write_calls") == 0,
                f"cold product recovery failed: {recovery_after}")
        cold_state = open_targets(device)
        require(cold_state.get("target_state_generation") ==
                generation_before + 2,
                f"cold Target generation mismatch: {cold_state}")
        cold_ready = connect(device, "cold-connect", MUTATION_SCOPES)
        require(cold_ready.get("status") == "ready",
                f"cold mutation reconnect failed: {cold_ready}")
        cold_target, cold_pages = target_by_id(device, target_id)
        require(cold_target.get("revision") == revision_before + 2 and
                cold_target.get("favorite") is favorite_before,
                f"cold restored value mismatch: {cold_target}")
        final_home = action(device, "left")
        require(final_home.get("page") == "home" and
                final_home.get("runtime_owner") == "none" and
                final_home.get("lease_mask") == 0,
                f"final Targets release failed: {final_home}")
        released = query(device, b"targets.state",
                         "leshy.targets.product.v1", "state")
        require(released.get("status") == "not_loaded" and
                released.get("workspace_allocated") is False and
                released.get("lease_mask") == 0,
                f"Targets workspace leaked: {released}")
        safe = query(device, b"hardware.safe-outputs",
                     "leshy.hardware.safe-outputs.v1", "state")
        inputs = query(device, b"input.state",
                       "leshy.input.frontend.v1", "state")
        metrics_after = query(device, b"metrics", "leshy.boot.v1", "ready")
        require(safe.get("buzzer_inactive") is True and
                safe.get("nrf_ce_inactive") is True and
                safe.get("software_quiesce_complete") is True,
                f"safe outputs violated: {safe}")
        require(inputs.get("read_errors") == 0 and
                inputs.get("queue_drops") == 0,
                f"input regression: {inputs}")
        cleanup = best_effort_cleanup(device)
        require(cleanup.get("complete") is True,
                f"final cleanup failed: {cleanup}")

        record.update({
            "status": "pass",
            "checkpoint": "complete",
            "exact_cid": EXPECTED_CID,
            "metrics_before": metrics_before,
            "metrics_after": metrics_after,
            "boot_recovery": recovery,
            "boot_recovery_after": recovery_after,
            "connection": ready,
            "target_id": target_id,
            "favorite_before": favorite_before,
            "favorite_restored": favorite_before,
            "revision_before": revision_before,
            "revision_after": revision_before + 2,
            "generation_before": generation_before,
            "generation_after": generation_before + 2,
            "negative": {
                "home_denied": home_denied,
                "no_op": no_op,
                "stale_revision": stale,
                "unknown_confirm": unknown_confirm,
                "changed_token": wrong_confirm,
                "replayed_confirm": replay_confirm,
                "revoked_after_exit": revoked,
            },
            "first": {
                "preview": first_preview,
                "confirm": first_confirm,
                "terminal": first_terminal,
                "status_samples": first_status_samples,
                "state": first_state,
                "list_pages": list_after,
            },
            "restore": {
                "preview": second_preview,
                "confirm": second_confirm,
                "terminal": second_terminal,
                "status_samples": second_status_samples,
                "state": second_state,
                "list_pages": list_restored,
            },
            "cold": {
                "target": cold_target,
                "list_pages": cold_pages,
                "reset": reset_timing,
            },
            "initial_list_pages": list_before,
            "released": released,
            "safe_outputs": safe,
            "input": inputs,
            "cleanup": cleanup,
            "radio_tx_commands": 0,
            "expected_atomic_commits": 2,
            "expected_write_calls_per_commit": 3,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(json.dumps({
            "schema": SCHEMA,
            "status": "pass",
            "run": str(args.output / "run.json"),
            "target_id": target_id,
            "generation": [generation_before, generation_before + 2],
            "revision": [revision_before, revision_before + 2],
            "ports_opened": [args.port],
        }, sort_keys=True))
        return 0
    except Exception as error:
        if device is not None and not cleanup.get("attempted"):
            try:
                cleanup = best_effort_cleanup(device)
            except Exception as cleanup_error:
                cleanup = {
                    "attempted": True,
                    "complete": False,
                    "errors": [
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    ],
                }
        record.update({
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
            "cleanup": cleanup,
        })
        write_json(args.output / "run.json", record)
        artifact_manifest(args.output)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    finally:
        if device is not None:
            device.close()


if __name__ == "__main__":
    raise SystemExit(main())
