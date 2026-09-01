#!/usr/bin/env python3
"""One-flash WF-15 HIL: bounded Wi-Fi PCAP into the real extcap client."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from capture_1x_ui import PassiveSerial, synchronize_console
from esp_app_identity import app_elf_sha256
from leshy_extcap import LivePcapClient, stream_live_pcap
from run_1x_prerelease_hil import flash_candidate, sha256_file, write_json
from run_1x_product_home_hil import stabilized_boot_metrics
from run_1x_product_survey_hil import (
    action,
    artifact_manifest,
    best_effort_cleanup,
    boot_failures,
    capture,
    expect,
    query,
    valid_cid,
)
from run_1x_wifi_frame_capture_hil import (
    STATE_SCHEMA,
    parse_pcap,
    select_home_app,
    wait_capture,
)


RUN_SCHEMA = "leshy.live_companion_wifi_hil.run.v1"
RESPONSE_SCHEMA = "leshy.companion.response.v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_only_query(device: PassiveSerial, command: bytes, schema: str,
                    kind: str, *, maximum_attempts: int = 3,
                    timeout: float = 5.0) -> dict[str, Any]:
    """Retry a lost read-only diagnostic reply without replaying UI input."""
    errors: list[str] = []
    for attempt in range(1, maximum_attempts + 1):
        try:
            record = query(device, command, schema, kind, timeout=timeout)
            record["host_transport_attempts"] = attempt
            record["host_transport_transient_retries"] = attempt - 1
            record["host_transport_transient_errors"] = errors
            return record
        except TimeoutError as error:
            if attempt == maximum_attempts:
                raise
            errors.append(str(error))
            device.reset_input_buffer()
            synchronize_console(device, 10.0)
    raise RuntimeError("unreachable read-only query retry state")


class ExistingSerialTransport:
    """Use the runner's one exclusive DUT port; never enumerate another port."""

    def __init__(self, device: PassiveSerial) -> None:
        self.device = device
        self.requests: list[dict[str, Any]] = []

    def exchange(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(dict(request))
        payload = (json.dumps(request, separators=(",", ":")) + "\n").encode(
            "ascii")
        self.device.write(payload)
        self.device.flush()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            line = self.device.readline()
            if not line:
                continue
            try:
                response = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if (isinstance(response, dict) and
                    response.get("schema") == RESPONSE_SCHEMA and
                    response.get("request_id") == request["request_id"]):
                return response
        raise TimeoutError(f"companion response timed out: {request['request_id']}")

    def close(self) -> None:
        # The outer HIL context exclusively owns and closes the physical port.
        return None


def tshark_summary(payload: bytes) -> dict[str, Any]:
    executable = shutil.which("tshark")
    app_binary = Path("/Applications/Wireshark.app/Contents/MacOS/tshark")
    if executable is None and app_binary.is_file():
        executable = str(app_binary)
    require(executable is not None, "Wireshark/tshark is required for WF-15 HIL")
    completed = subprocess.run(
        [executable, "-r", "-", "-T", "fields", "-e", "frame.number"],
        input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    require(completed.returncode == 0,
            f"tshark rejected live PCAP: {completed.stderr[:400]!r}")
    records = [line for line in completed.stdout.splitlines() if line]
    return {
        "accepted": True,
        "records": len(records),
        "payload_retained": False,
        "stderr_empty": completed.stderr == b"",
        "executable_name": Path(executable).name,
    }


def exact_source(root: Path, source_commit: str) -> None:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root, check=True, stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if head != source_commit or status:
        raise RuntimeError(
            "WF-15 HIL requires a clean checkout at the exact source commit")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--map", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-cid", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--reuse-exact-flash", action="store_true")
    parser.add_argument("--flash-baud", type=int, default=460800)
    args = parser.parse_args()

    if args.output.exists():
        parser.error("--output must not exist")
    for artifact in (args.firmware, args.elf, args.map):
        if not artifact.is_file():
            parser.error(f"candidate artifact missing: {artifact}")
    if not valid_cid(args.expected_cid):
        parser.error("--expected-cid must be exact uppercase hexadecimal CID")
    if len(args.source_commit) != 40:
        parser.error("--source-commit must be a full commit ID")
    if args.flash == args.reuse_exact_flash:
        parser.error("choose exactly one of --flash or --reuse-exact-flash")

    root = Path(__file__).resolve().parents[1]
    try:
        exact_source(root, args.source_commit)
    except RuntimeError as error:
        parser.error(str(error))

    args.output.mkdir(parents=True)
    frames = args.output / "frames"
    frames.mkdir()
    candidate = args.output / "firmware.bin"
    retained_elf = args.output / "firmware.elf"
    retained_map = args.output / "firmware.map"
    shutil.copyfile(args.firmware, candidate)
    shutil.copyfile(args.elf, retained_elf)
    shutil.copyfile(args.map, retained_map)
    app_identity = app_elf_sha256(candidate)
    failures: list[str] = []
    reports: dict[str, Any] = {}
    screenshots: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    raw_payload: bytes | None = None

    record: dict[str, Any] = {
        "schema": RUN_SCHEMA,
        "status": "in_progress",
        "run_id": secrets.token_hex(16),
        "source_commit": args.source_commit,
        "target": {
            "board_id": "board-01",
            "port": args.port,
            "ports_opened": [args.port],
            "serial_port_discovery_calls": 0,
            "cardputer_ports_opened": 0,
            "clone_ports_opened": 0,
        },
        "candidate": {
            "version": args.expected_version,
            "firmware_sha256": sha256_file(candidate),
            "firmware_bytes": candidate.stat().st_size,
            "elf_sha256": sha256_file(retained_elf),
            "map_sha256": sha256_file(retained_map),
            "app_elf_sha256": app_identity,
            "flashed": args.flash,
            "exact_flash_reused": args.reuse_exact_flash,
        },
        "policy": {
            "read_only_companion": True,
            "capture_started_only_by_user_ui_action": True,
            "companion_radio_start_commands": 0,
            "companion_radio_stop_commands": 0,
            "companion_tx_commands": 0,
            "host_network_tools_invoked": False,
            "active_mac_wifi_touched": False,
            "host_ble_advertising_started": False,
            "storage_writes_requested": 0,
        },
    }
    write_json(args.output / "run.json", record)

    try:
        if args.flash:
            flash_candidate(args.port, candidate, 0x10000, args.flash_baud)
            time.sleep(0.5)
        with PassiveSerial(args.port, 115200, timeout=0.15) as device:
            try:
                synchronize_console(device, 30.0)
                ready, samples = stabilized_boot_metrics(device)
                recovery = query(
                    device, b"storage.product.boot-recovery",
                    "leshy.storage.product_boot_recovery.v1", "state")
                failures.extend(boot_failures(
                    ready, recovery, args.expected_version, app_identity,
                    args.expected_cid))
                require(not failures, "exact boot identity failed")
                reports["boot"] = {"ready": ready, "samples": samples,
                                   "recovery": recovery}
                reports["cleanup_before"] = best_effort_cleanup(device)
                require(reports["cleanup_before"].get("complete") is True,
                        "initial Home/zero-lease cleanup failed")
                query(device, b"ui.language ru", "leshy.ui.v1", "state")

                home = select_home_app(device, "capture", trace)
                failures.extend(expect(home, {
                    "page": "home", "selection": 4,
                    "selected_id": "capture", "runtime_owner": "none",
                    "lease_mask": 0,
                }, "home_capture"))
                source_menu = action(device, "right")
                trace.append(source_menu)
                failures.extend(expect(source_menu, {
                    "page": "capture", "runtime_owner": "capture",
                    "lease_mask": 11, "capture_source_selection": 0,
                }, "source_menu"))
                screenshots["source_menu"] = capture(
                    device, frames, "live-companion-source-menu")
                trace.append(action(device, "right"))
                setup = query(device, b"capture.state", STATE_SCHEMA, "state")
                failures.extend(expect(setup, {
                    "state": "idle", "passive_only": True, "rx_only": True,
                    "storage_written": False, "lease_mask": 11,
                }, "setup"))
                reports["setup"] = setup
                screenshots["setup"] = capture(
                    device, frames, "live-companion-setup")

                started = action(device, "right")
                trace.append(started)
                running = wait_capture(
                    device,
                    lambda value: value.get("state") == "running" and
                    int(value.get("frames_accepted", 0)) >= 1,
                    5.0, "live Wi-Fi capture received no frame")
                failures.extend(expect(running, {
                    "state": "running", "passive_only": True,
                    "rx_only": True, "application_connect_calls": 0,
                    "application_raw_tx_calls": 0,
                    "storage_written": False, "lease_mask": 11,
                }, "running"))
                reports["running"] = running
                time.sleep(0.55)
                screenshots["running"] = capture(
                    device, frames, "live-companion-running")

                transport = ExistingSerialTransport(device)
                client = LivePcapClient(transport)
                stream = io.BytesIO()
                extcap_result = stream_live_pcap(client, stream)
                raw_payload = stream.getvalue()
                request_kinds = [item.get("kind") for item in transport.requests]
                require(request_kinds and request_kinds[0] == "connect" and
                        set(request_kinds[1:]) == {"capture.live.read"},
                        f"extcap issued a non-read command: {request_kinds}")
                require(all(set(item) <= {
                    "schema", "kind", "request_id", "protocol", "scopes",
                    "offset"} for item in transport.requests),
                    "extcap request widened its command surface")
                complete = wait_capture(
                    device, lambda value: value.get("state") == "complete",
                    3.0, "live stream did not reach terminal capture cleanup")
                failures.extend(expect(complete, {
                    "state": "complete", "cleanup_complete": True,
                    "driver_error": 0, "storage_written": False,
                    "pcap_available": True, "lease_mask": 9,
                }, "complete"))
                require(extcap_result["frames"] == complete["frames_accepted"],
                        "extcap frame count differs from device accounting")
                require(extcap_result["dropped"] ==
                        complete["frames_dropped_capacity"] +
                        complete["frames_dropped_invalid"],
                        "extcap drop count differs from device accounting")
                # ESP-IDF reports the FCS only when the complete frame fits in
                # the bounded snap length.  Truncated records must therefore
                # clear the Radiotap FCS-present bit; a real capture may
                # legitimately contain both record classes.
                pcap, pcap_failures = parse_pcap(
                    raw_payload, expected_fcs_included=None)
                failures.extend(pcap_failures)
                require(pcap.get("records") == complete["frames_accepted"],
                        "PCAP record count differs from accepted frames")
                wireshark = tshark_summary(raw_payload)
                require(wireshark["records"] == complete["frames_accepted"],
                        "Wireshark record count differs from device accounting")
                reports["live_companion"] = {
                    "connect_scopes": ["capture.live.read"],
                    "granted_capabilities": ["capture.live.wifi"],
                    "requests": len(transport.requests),
                    "read_requests": len(transport.requests) - 1,
                    "stream": extcap_result,
                    "pcap": pcap,
                    "wireshark": wireshark,
                    "sha256": hashlib.sha256(raw_payload).hexdigest(),
                    "raw_payload_retained": False,
                }
                reports["complete"] = complete
                screenshots["result"] = capture(
                    device, frames, "live-companion-result")

                trace.append(action(device, "left"))
                trace.append(action(device, "left"))
                final = query(device, b"ui.state", "leshy.ui.v1", "state")
                failures.extend(expect(final, {
                    "page": "home", "runtime_owner": "none", "lease_mask": 0,
                }, "final"))
                scrubbed = query(device, b"capture.state", STATE_SCHEMA, "state")
                failures.extend(expect(scrubbed, {
                    "state": "idle", "frames_reported": 0,
                    "frames_accepted": 0, "payload_bytes": 0,
                    "pcap_available": False, "lease_mask": 0,
                }, "scrubbed"))
                reports["final"] = final
                reports["scrubbed"] = scrubbed
                reports["safe_outputs"] = read_only_query(
                    device, b"hardware.safe-outputs",
                    "leshy.hardware.safe-outputs.v1", "state")
                reports["input"] = read_only_query(
                    device, b"input.state", "leshy.input.frontend.v1", "state")
                screenshots["home"] = capture(
                    device, frames, "live-companion-home")
            finally:
                raw_payload = None
                reports["cleanup_after"] = best_effort_cleanup(device)
                if reports["cleanup_after"].get("complete") is not True:
                    failures.append("final cleanup did not prove Home/zero lease")
    except Exception as error:
        failures.append(f"workflow: {type(error).__name__}: {error}")

    record.update({
        "status": "pass" if not failures else "failed",
        "passed": not failures,
        "failures": failures,
        "reports": reports,
        "screenshots": screenshots,
        "trace": trace,
        "privacy": {
            "ambient_ssid_retained": False,
            "ambient_bssid_retained": False,
            "raw_80211_payload_retained": False,
            "raw_pcap_retained": False,
            "retained_pcap_material": "hash_counts_channel_rssi_bounds_only",
        },
    })
    write_json(args.output / "run.json", record)
    artifact_manifest(args.output)
    print(json.dumps({
        "schema": RUN_SCHEMA,
        "passed": record["passed"],
        "failures": failures,
        "run": str(args.output / "run.json"),
    }, sort_keys=True))
    return 0 if record["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
