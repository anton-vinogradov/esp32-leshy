#!/usr/bin/env python3
"""Retain privacy-minimal, machine-checked FF-0 physical review evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256
import run_1x_top_level_menu_smoke_hil as runner


ROOT = Path(__file__).resolve().parents[1]
CID = "FE343253440000002000000055019CB7"
MENU_IDS = [case.item_id for case in runner.MENU_CASES]
EVIDENCE_IDS = ["E-BUILD-211", "E-AUTO-186", "E-HIL-219", "E-UX-070",
                "RB-M222"]
FINAL_SOURCE = "65402c4f2de77a8568e07e0e14ea9382d6123589"
BASELINE_RUNNER_COMMIT = "da429b6"
LAB_RUNNER_COMMIT = "ec92590"
EXPECTED = {
    "baseline": {
        "version": "1.0.0-dev.308",
        "source": "c70ab42739faab639b65c2fb77905718921fa676",
        "firmware": "d68155a47d47181547843d1ab2f89056fd98a5ce5863a05846604fae2637e866",
        "runner": "285b8ff818c649e9b02e661f9c6e353553997e2e52bde789840f9e2cd1636540",
        "run": "bf68b4929fc67519ce7e1958f8f9d39feb411de780125ce65ba948509d15fcc2",
    },
    "lab": {
        "version": "1.0.0-dev.309",
        "source": "ec9259010709fbe0ae6dccbb90a416635f997a46",
        "firmware": "7d7b6d2ad4729766d3cf1ed4db0e0a2a715ac93551c3f2b077263402d0e70d33",
        "runner": "c0cc7330a9077153a8bd4296aca5a42637dfdf27304c37916ca2504d75e8bfcb",
        "run": "3c6841281a705e11fb7631a4d1d52e991327a98aa613a58a81370b9926a32dc5",
        "png": "cbd15c75515607dff82499ef3d648e93550a971f53ea4461dea8a7b168260b32",
        "rgb": "b7f309caa8c5414d9f659dfc5785e097838e664723c0802167c979d697b24ea4",
    },
    "wrapped": {
        "version": "1.0.0-dev.310",
        "source": "b03c154c8540f4829efed7d482305535e85050fb",
        "firmware": "3f8cbd02e0790ff2fdc925067910c354fc316e405f539ba33aab137d30ddc3fd",
        "run": "ae597e1949c15b1aa7e57d79d02de6f576a61e918e3259e8f20aa41b1c0a656b",
        "png": "351d9d0ab4db204ecb38e6edad4b3623733bf6ff835691ee8ab4b35a451ae224",
    },
    "final": {
        "version": "1.0.0-dev.311",
        "source": FINAL_SOURCE,
        "firmware": "0b749437c42b192bb3148f0cb3f248c676ac7b49c6735e58e0645ae94c8e964b",
        "app_elf": "ccdaec43a12863259194f49c42624963c3e7145ad6208b555bd152ef8b1699f7",
        "factory": "dce42aa071d4937cf8009ab8b32d28d3c5d007d03cbef2e927e7fe5e8ebaef34",
        "map": "6d2551841095e2af5ec624bfc10250bcb7e2f6d6903696eca0962eb05c8bee6c",
        "runner": "c0a7c7ca766d7e055be4dee960f5d1ed283640f8c7191ae39eb61f265a8934e1",
        "run": "99a0d948edfad4ca42917065291f7f0cc5e8c62a677a3761ec38892cc93a0102",
        "png": "36712b81fecad7edb446ba2152022ed70bde4659fbbeaa3ed683b27c6f9c88e6",
        "rgb": "92ce49d633d6973698e4364d0ba0dc29412c01ccd993bf141b104a6eda53d3f3",
    },
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git_blob_digest(commit: str, path: str) -> str:
    blob = subprocess.check_output(["git", "show", f"{commit}:{path}"],
                                   cwd=ROOT)
    return hashlib.sha256(blob).hexdigest()


def validate_terminal(run: dict[str, Any], name: str) -> None:
    final = run.get("post_hil_end", {})
    ui = final.get("ui", {})
    require(run.get("passed") is True and run.get("failures") == [] and
            run.get("cleanup_after", {}).get("complete") is True and
            run.get("safe_outputs", {}).get("buzzer_inactive") is True and
            run.get("safe_outputs", {}).get("nrf_ce_inactive") is True and
            run.get("safe_outputs", {}).get(
                "software_quiesce_complete") is True and
            run.get("input", {}).get("read_errors") == 0 and
            run.get("input", {}).get("queue_drops") == 0 and
            final.get("hil", {}).get("active") is False and
            ui.get("page") == "home" and ui.get("runtime_owner") == "none" and
            ui.get("lease_mask") == 0,
            f"{name}: terminal safety/cleanup mismatch")


def validate_candidate(run: dict[str, Any], expected: dict[str, str],
                       name: str) -> None:
    candidate = run.get("candidate", {})
    require(candidate.get("version") == expected["version"] and
            candidate.get("source_commit") == expected["source"] and
            candidate.get("firmware_sha256") == expected["firmware"] and
            candidate.get("verified") is True and
            run.get("expected_cid") == CID,
            f"{name}: candidate/CID mismatch")


def validate_screen(screen: dict[str, Any], *, item_id: str,
                    png: str | None = None, rgb: str | None = None) -> None:
    frame = screen.get("frame_begin", {})
    state = screen.get("state", {})
    require((frame.get("width"), frame.get("height"), frame.get("bytes")) ==
            (240, 320, 153600) and
            state.get("selected_id") == item_id and
            state.get("safety_latched") is False and
            screen.get("transport_transient_retries") == 0,
            f"{item_id}: invalid screenshot geometry/state")
    if png is not None:
        require(screen.get("png_sha256") == png, f"{item_id}: PNG mismatch")
    if rgb is not None:
        require(screen.get("rgb565_sha256") == rgb,
                f"{item_id}: RGB565 mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--lab", required=True, type=Path)
    parser.add_argument("--wrapped", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--factory", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()

    paths = {name: value.resolve() for name, value in (
        ("baseline", args.baseline), ("lab", args.lab),
        ("wrapped", args.wrapped), ("final", args.final))}
    run_paths = {name: path / "run.json" for name, path in paths.items()}
    destination = args.destination.resolve()
    bundle = destination.with_suffix("")
    required = (*run_paths.values(), args.firmware.resolve(),
                args.factory.resolve(), args.elf.resolve(), args.map.resolve())
    require(all(path.is_file() for path in required), "input artifact missing")
    require(not destination.exists() and not bundle.exists(),
            "retained destination already exists")

    runs = {name: load(path) for name, path in run_paths.items()}
    for name, run in runs.items():
        require(digest(run_paths[name]) == EXPECTED[name]["run"],
                f"{name}: raw run digest mismatch")
        validate_candidate(run, EXPECTED[name], name)
        validate_terminal(run, name)

    baseline = runs["baseline"]
    require(baseline.get("runner_source_sha256") == EXPECTED["baseline"]["runner"] and
            git_blob_digest(BASELINE_RUNNER_COMMIT,
                            "tools/run_1x_top_level_menu_smoke_hil.py") ==
                EXPECTED["baseline"]["runner"] and
            [record.get("id") for record in baseline.get("menus", [])] ==
                MENU_IDS and
            all(record.get("passed") is True and record.get("failures") == []
                for record in baseline.get("menus", [])) and
            set(baseline.get("screens", {})) == set(MENU_IDS),
            "baseline: complete catalog review mismatch")
    for item_id in MENU_IDS:
        validate_screen(baseline["screens"][item_id], item_id=item_id)

    lab = runs["lab"]
    require(lab.get("runner_source_sha256") == EXPECTED["lab"]["runner"] and
            git_blob_digest(LAB_RUNNER_COMMIT,
                            "tools/run_1x_top_level_menu_smoke_hil.py") ==
                EXPECTED["lab"]["runner"] and
            lab.get("policy", {}).get("requested_menu_ids") ==
                ["targets", "lab"],
            "lab: strict delta lineage mismatch")
    validate_screen(lab["screens"]["lab"], item_id="lab",
                    png=EXPECTED["lab"]["png"], rgb=EXPECTED["lab"]["rgb"])

    wrapped = runs["wrapped"]
    validate_screen(wrapped["screens"]["targets"], item_id="targets",
                    png=EXPECTED["wrapped"]["png"])

    final = runs["final"]
    require(runner.result_contract_failures(final) == [] and
            final.get("runner_source_sha256") == EXPECTED["final"]["runner"] and
            digest(args.firmware.resolve()) == EXPECTED["final"]["firmware"] and
            digest(args.factory.resolve()) == EXPECTED["final"]["factory"] and
            digest(args.elf.resolve()) == EXPECTED["final"]["app_elf"] and
            app_elf_sha256(args.firmware.resolve()) ==
                EXPECTED["final"]["app_elf"] and
            digest(args.map.resolve()) == EXPECTED["final"]["map"],
            "final: independent contract/build binding mismatch")
    target = next(record for record in final["menus"]
                  if record.get("id") == "targets")
    state = target.get("feature_state", {})
    require({key: state.get(key) for key in (
                "status", "workspace_allocated", "page_open",
                "identity_attempts", "identity_cleanup_complete",
                "filesystem_mount_attempts", "filesystem_mount_error",
                "cleanup_complete", "blocked_write_attempts", "lease_mask")}
            == {
                "status": "session_unavailable", "workspace_allocated": False,
                "page_open": True, "identity_attempts": 1,
                "identity_cleanup_complete": True,
                "filesystem_mount_attempts": 1, "filesystem_mount_error": 0,
                "cleanup_complete": True, "blocked_write_attempts": 0,
                "lease_mask": 13,
            }, "final: truthful empty Targets state mismatch")
    validate_screen(final["screens"]["targets"], item_id="targets",
                    png=EXPECTED["final"]["png"],
                    rgb=EXPECTED["final"]["rgb"])

    bundle.mkdir(parents=True)
    frames = bundle / "frames"
    frames.mkdir()
    safe_frames = {
        "automation-empty.png": paths["lab"] / "frames/07-lab.png",
        "targets-empty.png": paths["final"] / "frames/05-targets.png",
    }
    for name, source in safe_frames.items():
        shutil.copy2(source, frames / name)

    evidence = {
        "schema": "leshy.functional_review.acceptance.v1",
        "status": "pass",
        "board": "board-01",
        "cid": CID,
        "evidence_ids": EVIDENCE_IDS,
        "candidate": {
            "version": EXPECTED["final"]["version"],
            "source_commit": FINAL_SOURCE,
            "firmware_sha256": digest(args.firmware.resolve()),
            "factory_sha256": digest(args.factory.resolve()),
            "elf_sha256": digest(args.elf.resolve()),
            "map_sha256": digest(args.map.resolve()),
            "firmware_bytes": args.firmware.stat().st_size,
            "factory_bytes": args.factory.stat().st_size,
            "static_ram_bytes": 233632,
            "linked_flash_bytes": 3563180,
            "ota_free_bytes": 4194304 - args.firmware.stat().st_size,
        },
        "review": {
            "baseline_version": EXPECTED["baseline"]["version"],
            "baseline_run_sha256": digest(run_paths["baseline"]),
            "catalog_order": MENU_IDS,
            "top_level_routes_reviewed": len(MENU_IDS),
            "automatic_screens_captured": len(baseline["screens"]),
            "ambient_frames_retained": False,
            "ambient_frame_digests": {
                item_id: {
                    "png_sha256": baseline["screens"][item_id]["png_sha256"],
                    "rgb565_sha256": baseline["screens"][item_id]["rgb565_sha256"],
                } for item_id in MENU_IDS
            },
            "privacy_note": (
                "Ambient Wi-Fi/BLE frame bytes are intentionally not retained; "
                "only their machine-checked digests and lifecycle evidence remain."
            ),
        },
        "accepted_corrections": {
            "automation": {
                "version": EXPECTED["lab"]["version"],
                "run_sha256": digest(run_paths["lab"]),
                "frame": "frames/automation-empty.png",
                "png_sha256": digest(frames / "automation-empty.png"),
                "outcome": "actionable missing-SD state; internal path removed; execution off",
            },
            "targets": {
                "version": EXPECTED["final"]["version"],
                "run_sha256": digest(run_paths["final"]),
                "frame": "frames/targets-empty.png",
                "png_sha256": digest(frames / "targets-empty.png"),
                "feature_status": state["status"],
                "sd_identity_attempts": state["identity_attempts"],
                "sd_mount_attempts": state["filesystem_mount_attempts"],
                "sd_mount_error": state["filesystem_mount_error"],
                "blocked_write_attempts": state["blocked_write_attempts"],
                "outcome": "truthful empty state and one-line next action",
            },
        },
        "rejected_visual_predecessor": {
            "version": EXPECTED["wrapped"]["version"],
            "run_sha256": digest(run_paths["wrapped"]),
            "hil_contract_passed": True,
            "accepted": False,
            "reason": "Russian Bluetooth hint wrapped its final two letters",
            "png_sha256": EXPECTED["wrapped"]["png"],
        },
        "terminal": {
            "page": "home", "runtime_owner": "none", "lease_mask": 0,
            "hil_active": False, "input_read_errors": 0,
            "input_queue_drops": 0, "buzzer_inactive": True,
            "nrf_ce_inactive": True, "dangerous_tx_started": False,
            "mac_wifi_or_ble_controlled": False, "manual_button_presses": 0,
            "clone_or_cardputer_touched": False,
        },
        "scope": {
            "accepts": [
                "FF-0 physical top-level product review on all nine routes",
                "automatic screenshots and lifecycle cleanup",
                "actionable Automation and truthful empty Targets states",
            ],
            "does_not_accept": [
                "nested feature completeness or calibrated RF accuracy",
                "flicker under every live-update workload",
                "release endurance or periodic full HIL",
            ],
            "focused_cadence": "5/15",
            "next": "FF-1 FUNC-17 Radar/localize vertical slice",
        },
    }
    destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": "pass", "destination": str(destination),
                      "bundle": str(bundle)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
