#!/usr/bin/env python3
"""Fail-closed checker for retained CAP049 persistence/export evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path
from typing import Any

from esp_app_identity import app_elf_sha256


ROOT = Path(__file__).resolve().parents[1]
CHECKER = Path(__file__).resolve()
RUNNER = ROOT / "tools/run_1x_wifi_authentication_persistence_hil.py"
RUN_SCHEMA = "leshy.wifi.authentication_persistence_hil.run.v1"
EXPECTATIONS_SCHEMA = \
    "leshy.wifi.authentication_persistence_hil.expectations.v1"
CID = "FE343253440000002000000055019CB7"
BOARD = "board-01"
EVIDENCE = ROOT / "tests/hil/evidence"
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
SESSION = re.compile(r"[0-9a-f]{32}")
MAC = re.compile(r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")
PRIVATE_KEYS = frozenset({
    "target_bssid", "target_identity_hash", "identity_hash", "ssid",
    "bssid", "target_label", "wifi_network_selected_identity_hash",
    "wifi_network_order_hash", "wifi_device_order_hash",
})


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def committed_file_sha256(commit: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise OSError(detail or f"cannot read {path} from source commit")
    return hashlib.sha256(result.stdout).hexdigest()


def require(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def load_json(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"{label}: {error}")
        return {}
    if not isinstance(value, dict):
        failures.append(f"{label}: JSON object required")
        return {}
    return value


def verify_private_absent(failures: list[str], value: Any,
                          path: str = "run") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            require(failures, not isinstance(key, str) or
                    key.lower() not in PRIVATE_KEYS,
                    f"{path}.{key}: private target key retained")
            verify_private_absent(failures, item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            verify_private_absent(failures, item, f"{path}[{index}]")
    elif isinstance(value, str):
        require(failures, MAC.search(value) is None,
                f"{path}: MAC-like identifier retained")


def verify_manifest(bundle: Path, failures: list[str]) -> dict[str, str]:
    index = bundle / "artifacts.sha256"
    if not index.is_file() or index.is_symlink():
        failures.append("artifacts.sha256: regular file required")
        return {}
    entries: dict[str, str] = {}
    try:
        lines = index.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        failures.append(f"artifacts.sha256: {error}")
        return {}
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            failures.append(f"artifacts.sha256:{number}: malformed")
            continue
        expected, name = match.groups()
        relative = Path(name)
        if (relative.is_absolute() or ".." in relative.parts or
                name in entries or name == "artifacts.sha256"):
            failures.append(f"artifacts.sha256:{number}: unsafe {name!r}")
            continue
        target = bundle / relative
        require(failures, target.is_file() and not target.is_symlink(),
                f"artifact missing: {name}")
        if target.is_file():
            require(failures, digest(target) == expected,
                    f"artifact hash mismatch: {name}")
        entries[name] = expected
    actual = {
        item.relative_to(bundle).as_posix()
        for item in bundle.rglob("*")
        if item.is_file() and item != index
    }
    require(failures, set(entries) == actual,
            "artifacts.sha256: exact inventory mismatch")
    require(failures, set(entries) == {"firmware.bin", "run.json"},
            "evidence must retain only firmware.bin and sanitized run.json")
    return entries


def verify_cleanup(failures: list[str], cleanup: Any, label: str) -> None:
    require(failures, isinstance(cleanup, dict) and
            cleanup.get("complete") is True,
            f"{label}: cleanup proof missing")


def verify_boot(failures: list[str], boot: Any, *, version: str,
                app: str, generation: int, label: str) -> None:
    require(failures, isinstance(boot, dict), f"{label}: object required")
    if not isinstance(boot, dict):
        return
    ready = boot.get("ready", {})
    recovery = boot.get("recovery", {})
    require(failures, ready.get("schema") == "leshy.boot.v1" and
            ready.get("kind") == "ready" and
            ready.get("version") == version and
            ready.get("app_elf_sha256") == app and
            ready.get("buzzer_inactive") is True,
            f"{label}.ready: exact safe candidate boot required")
    require(failures,
            recovery.get("schema") ==
                "leshy.storage.product_boot_recovery.v1" and
            recovery.get("kind") == "state" and
            recovery.get("status") == "admitted" and
            recovery.get("generation") == generation and
            recovery.get("fingerprint_matched") is True and
            recovery.get("observed_fingerprint") == CID and
            recovery.get("integrity") == "valid" and
            recovery.get("mounted_read_only") is True and
            recovery.get("read_only_guaranteed") is True and
            recovery.get("write_enabled") is False and
            recovery.get("physical_write_calls") == 0 and
            recovery.get("blocked_write_attempts") == 0 and
            recovery.get("cleanup_complete") is True,
            f"{label}.recovery: read-only CID-bound recovery mismatch")


def verify_run(run: dict[str, Any], marker: dict[str, Any],
               failures: list[str]) -> None:
    require(failures, run.get("schema") == RUN_SCHEMA and
            run.get("passed") is True and
            run.get("gate_eligible") is True and run.get("failures") == [],
            "run: clean gate-eligible pass required")
    require(failures, isinstance(run.get("run_id"), str) and
            SESSION.fullmatch(run["run_id"]) is not None,
            "run.run_id: lowercase 32-hex required")
    require(failures, run.get("runner_source_sha256") ==
            marker.get("runner_source_sha256"),
            "run: runner hash mismatch")
    candidate = run.get("candidate", {})
    for field in ("version", "source_commit", "firmware_sha256",
                  "app_elf_sha256"):
        require(failures, candidate.get(field) == marker.get(field),
                f"candidate.{field}: exact pin mismatch")
    require(failures,
            ((candidate.get("flashed") is True and
              candidate.get("reused_exact_flash") is False) or
             (candidate.get("flashed") is False and
              candidate.get("reused_exact_flash") is True)),
            "candidate: exactly one fresh/reused flash mode required")
    board = run.get("board", {})
    require(failures, board == {
        "id": BOARD, "expected_cid": marker.get("expected_cid")},
        "board: exact board-01/CID binding required")

    fixture = run.get("fixture", {})
    loaded = fixture.get("load", {})
    replay = fixture.get("replay", {})
    state = fixture.get("state", {})
    persisted = fixture.get("persisted", {})
    require(failures,
            loaded.get("status") == "loaded" and
            loaded.get("fixture_frames") == 2 and
            loaded.get("profile") == "strict-m1-m2-raw-v1" and
            loaded.get("synthetic") is True and
            loaded.get("one_shot") is True and
            loaded.get("public_test_identifiers_only") is True and
            loaded.get("radio_started") is False and
            loaded.get("rf_hardware_touched") is False and
            loaded.get("connect_calls") == 0 and
            loaded.get("raw_tx_calls") == 0 and
            loaded.get("raw_payload_disclosed") is False,
            "fixture.load: deterministic RX/TX-inert fixture mismatch")
    require(failures,
            replay.get("status") == "replay_rejected" and
            replay.get("replayed") is True and
            replay.get("loaded") is False and
            replay.get("radio_started") is False and
            replay.get("rf_hardware_touched") is False,
            "fixture.replay: one-shot rejection missing")
    require(failures,
            state.get("report_origin") == "synthetic_hil_persistence" and
            state.get("synthetic") is True and
            state.get("passive") is True and
            state.get("tx_path") is False and
            state.get("connect_path") is False and
            state.get("frames_reported") == 2 and
            state.get("frames_accepted") == 2 and
            state.get("evidence") == 2 and state.get("peers") == 1 and
            state.get("controller_selected_peer_mask") == 3 and
            state.get("capture_cleanup_complete") is True and
            state.get("adapter_cleanup_complete") is True,
            "fixture.state: production analyzer proof mismatch")
    generation = persisted.get("generation")
    require(failures, isinstance(generation, int) and generation > 0,
            "fixture.persisted: positive generation required")
    if not isinstance(generation, int):
        generation = -1
    require(failures,
            persisted.get("status") == "saved" and
            persisted.get("store_kind") == "authentication" and
            persisted.get("capture_frames") == 2 and
            persisted.get("explicit_save") is True and
            persisted.get("atomic_commit") is True and
            persisted.get("reopen_verified") is True and
            persisted.get("pcap_ready") is True and
            persisted.get("hc22000_ready") is True and
            persisted.get("cleanup_complete") is True,
            "fixture.persisted: atomic authentication save mismatch")

    before_generation = run.get("boot_before", {}).get(
        "recovery", {}).get("generation")
    require(failures, isinstance(before_generation, int) and
            generation > before_generation,
            "generation: save did not advance persistent catalog")
    verify_boot(failures, run.get("boot_after"),
                version=str(marker.get("version", "")),
                app=str(marker.get("app_elf_sha256", "")),
                generation=generation, label="boot_after")

    metadata = run.get("library", {}).get("metadata", {})
    pcap = run.get("library", {}).get("pcap", {})
    hc = run.get("library", {}).get("hc22000", {})
    require(failures,
            metadata.get("generation") == generation and
            metadata.get("integrity") == "valid" and
            metadata.get("persistent") is True and
            metadata.get("immutable") is True and
            metadata.get("payload") == {
                "bytes": 284, "format": "ieee80211", "records": 2,
                "snap_length": 256, "status": "captured_raw_80211"} and
            metadata.get("exports", {}).get("pcap") ==
                "available_radiotap",
            "library.metadata: recovered raw capture mismatch")
    pcap_summary = pcap.get("summary", {})
    require(failures,
            pcap.get("begin", {}).get("bytes") == 370 and
            pcap.get("end", {}).get("frames") == 2 and
            pcap_summary.get("records") == 2 and
            pcap_summary.get("bytes") == 370 and
            pcap_summary.get("captured_frame_bytes") == 284 and
            pcap_summary.get("linktype") == 127 and
            pcap_summary.get("frequencies_mhz") == [2437] and
            pcap_summary.get("fcs_included_records") == 0 and
            pcap_summary.get("payload_retained") is False and
            SHA256.fullmatch(str(pcap_summary.get("sha256", ""))) is not None,
            "library.pcap: bounded radiotap export mismatch")
    hc_summary = hc.get("summary", {})
    require(failures,
            hc.get("begin", {}).get("bytes") == 408 and
            hc.get("end", {}).get("records") == 1 and
            hc.get("end", {}).get("eapol_records") == 1 and
            hc.get("end", {}).get("pmkid_records") == 0 and
            hc_summary.get("records") == 1 and
            hc_summary.get("format") == "WPA*02" and
            hc_summary.get("bytes") == 408 and
            SHA256.fullmatch(str(hc_summary.get("sha256", ""))) is not None,
            "library.hc22000: one canonical WPA*02 export required")

    begin = run.get("hil", {}).get("begin", {})
    end = run.get("hil", {}).get("end", {})
    require(failures, begin.get("status") == "begun" and
            end.get("status") == "ended" and
            begin.get("session_id") == end.get("session_id") ==
                run.get("run_id") and
            begin.get("app_elf_sha256") == marker.get("app_elf_sha256") and
            end.get("app_elf_sha256") == marker.get("app_elf_sha256"),
            "hil: exact session continuity mismatch")
    for label in ("cleanup_before", "cleanup_after_save", "cleanup_after"):
        verify_cleanup(failures, run.get(label), label)
    final = run.get("final", {})
    require(failures, final.get("page") == "home" and
            final.get("runtime_owner") == "none" and
            final.get("lease_mask") == 0 and
            final.get("library_generation") == generation and
            final.get("library_persistent") is True and
            final.get("library_simulated") is False,
            "final: Home/zero-lease persistent library proof missing")
    privacy = run.get("privacy", {})
    require(failures, privacy == {
        "authorized_ssid_hash_retained": False,
        "ambient_target_identifiers_retained": False,
        "raw_pcap_retained": False,
        "raw_hc22000_retained": False,
        "artifact_retention": "hashes_counts_and_format_only",
        "fixture_identifiers": "public_locally_administered_test_only",
    }, "privacy: exact sanitized retention contract required")
    verify_private_absent(failures, run)


def check(expectations: Path, positive: Path) -> list[str]:
    failures: list[str] = []
    require(failures, positive.is_dir() and not positive.is_symlink(),
            "positive: regular evidence directory required")
    require(failures, expectations.is_file() and not expectations.is_symlink(),
            "expectations: regular JSON file required")
    if failures:
        return failures
    for item in positive.rglob("*"):
        require(failures, not item.is_symlink(),
                f"positive: symlink rejected: {item}")
    marker = load_json(expectations, failures, "expectations")
    expected_fields = {
        "schema", "version", "expected_cid", "run_id", "source_commit",
        "firmware_sha256", "app_elf_sha256", "checker_source_sha256",
        "runner_source_sha256",
        "positive_run_sha256", "positive_artifact_index_sha256",
    }
    require(failures, set(marker) == expected_fields and
            marker.get("schema") == EXPECTATIONS_SCHEMA and
            marker.get("expected_cid") == CID and
            COMMIT.fullmatch(str(marker.get("source_commit", ""))) is not None and
            SESSION.fullmatch(str(marker.get("run_id", ""))) is not None and
            all(SHA256.fullmatch(str(marker.get(field, ""))) is not None
                for field in ("firmware_sha256", "app_elf_sha256",
                              "checker_source_sha256", "runner_source_sha256",
                              "positive_run_sha256",
                              "positive_artifact_index_sha256")),
            "expectations: exact pinned field contract required")
    try:
        source_runner_sha256 = committed_file_sha256(
            str(marker.get("source_commit", "")),
            RUNNER.relative_to(ROOT).as_posix(),
        )
    except OSError as error:
        failures.append(f"expectations: source-commit runner: {error}")
    else:
        require(failures,
                source_runner_sha256 == marker.get("runner_source_sha256"),
                "expectations: source-commit runner hash mismatch")
    entries = verify_manifest(positive, failures)
    run_path = positive / "run.json"
    index_path = positive / "artifacts.sha256"
    run = load_json(run_path, failures, "run")
    require(failures, run_path.is_file() and
            digest(run_path) == marker.get("positive_run_sha256"),
            "run.json: acceptance hash mismatch")
    require(failures, index_path.is_file() and
            digest(index_path) == marker.get("positive_artifact_index_sha256"),
            "artifacts.sha256: acceptance hash mismatch")
    require(failures, run.get("run_id") == marker.get("run_id"),
            "run_id: acceptance pin mismatch")
    verify_run(run, marker, failures)
    firmware = positive / "firmware.bin"
    require(failures, firmware.is_file() and
            entries.get("firmware.bin") == marker.get("firmware_sha256") and
            digest(firmware) == marker.get("firmware_sha256"),
            "firmware.bin: candidate/manifest binding mismatch")
    if firmware.is_file():
        try:
            embedded = app_elf_sha256(firmware)
        except (OSError, ValueError, struct.error) as error:
            failures.append(f"firmware.bin: invalid ESP app image: {error}")
        else:
            require(failures, embedded == marker.get("app_elf_sha256"),
                    "firmware.bin: embedded app identity mismatch")
    return failures


def evidence_paths(version: str) -> tuple[Path, Path]:
    stem = f"board-01-wifi-authentication-persistence-{version}"
    return EVIDENCE / stem, EVIDENCE / f"{stem}-acceptance.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--positive", type=Path)
    parser.add_argument("--expectations", type=Path)
    args = parser.parse_args(argv)
    default_positive, default_expectations = evidence_paths(args.version)
    args.positive = args.positive or default_positive
    args.expectations = args.expectations or default_expectations
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    failures = check(args.expectations, args.positive)
    if failures:
        print("\n".join(f"FAIL: {failure}" for failure in failures))
        return 1
    print(json.dumps({
        "schema": EXPECTATIONS_SCHEMA, "status": "pass",
        "version": args.version, "board": BOARD,
        "positive": str(args.positive.resolve()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
