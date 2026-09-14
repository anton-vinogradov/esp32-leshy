#!/usr/bin/env python3
"""Retain a privacy-minimal blocked two-product-DIV deployment, never a pass."""
import argparse
import hashlib
import json
from pathlib import Path
from esp_app_identity import app_elf_sha256


def retain_console_timeout(folder, deploy_log):
    """Bind a verified write followed by a silent console; infer no CPU cause."""
    image = (folder / 'firmware.bin').read_bytes()
    deploy = deploy_log.read_text()
    if deploy.count('Hash of data verified.') != 1 or 'TimeoutError: timed out synchronizing the firmware console' not in deploy:
        raise ValueError('expected one verified write and console synchronization failure')
    if f'Wrote {len(image)} bytes' not in deploy:
        raise ValueError('flash length differs from retained image')
    source = (folder / 'source-post-deploy-probe.log').read_bytes()
    reset = (folder / 'source-one-reset.log').read_bytes()
    if source or reset: raise ValueError('not a silent-console case; inspect new evidence')
    receiver_raw = (folder / 'receiver-post-deploy-probe.log').read_bytes()
    receiver = next(json.loads(line) for line in receiver_raw.splitlines()
        if line.startswith(b'{"schema":"leshy.ui.v1"'))
    if not (receiver['page'] == 'home' and receiver['lease_mask'] == 0 and not receiver['safety_latched']):
        raise ValueError('receiver not verified idle')
    boot_raw = (folder / 'source-boot.log').read_bytes()
    retry = [json.loads(line) for line in boot_raw.splitlines()
        if line.startswith(b'{"schema":"leshy.storage.product_boot_retry.v1"')]
    if not retry or any(not item['cleanup_complete'] or item['blocked_write_attempts'] != 0 for item in retry):
        raise ValueError('missing clean boot-retry evidence')
    paths = [deploy_log] + [folder / name for name in ('source-boot.log',
        'source-post-deploy-probe.log', 'receiver-post-deploy-probe.log', 'source-one-reset.log')]
    return dict(schema='leshy.wifi_product_boot.console_timeout.v1', status='blocked',
        two_board_acceptance=False, application_runtime_verified=False,
        app_elf_sha256=app_elf_sha256(folder / 'firmware.bin'),
        image_sha256=hashlib.sha256(image).hexdigest(), image_bytes=len(image),
        verified_flash_writes=1, test_network_started=False,
        observed_sd_retry_attempts=[item['completed_attempts'] for item in retry],
        source_post_flash_state='unknown; USB silent',
        receiver_state={key:receiver[key] for key in ('page','lease_mask','safety_latched')},
        receiver_flashed=False, controlled_reset_attempts=1,
        cause='Unconfirmed. Last serial output is a clean missing-media retry followed by ROM boot; silence does not distinguish a stalled application from a USB transport failure.',
        private_log_sha256={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
        limits='No new feature/cadence credit, no test AP or client positive. Do not infer a watchdog trip, SD defect, or safe final source state from a silent console.')


def retain(before, after):
    def records(path):
        result = []
        for line in path.read_text().splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict): result.append(value)
            except ValueError:
                pass
        return result

    observed = records(before / "source-postdeploy-safety.log")
    boot = next(v for v in observed if v.get("schema") == "leshy.boot.v1")
    safety = next(v for v in observed if v.get("schema") == "leshy.safety.v1")
    identity = app_elf_sha256(before / "firmware.bin")
    assert boot["app_elf_sha256"] == identity
    assert safety["watchdog_journal_app_elf_sha256"] == identity
    assert safety["latched"] and safety["reason"] == "runtime_watchdog"
    assert safety["watchdog_trace_valid"] and safety["watchdog_journal_nvs_verified"]
    assert safety["runtime_owner"] == "none" and safety["lease_mask"] == 0
    assert safety["buzzer_inactive"] and safety["nrf_ce_inactive"]
    retry = records(before / "source-clear-boot.log")
    attempts = [v["completed_attempts"] for v in retry
                if v.get("schema") == "leshy.storage.product_boot_retry.v1"]
    assert attempts == [1, 2, 3, 4]
    failed = (after / "source-deploy.log").read_text()
    assert "Failed to connect to ESP32-S3: No serial data received." in failed
    assert "Writing at" not in failed and "Hash of data verified" not in failed
    assert "'ready_ms': None" in (after / "source-usb-recovery.log").read_text()
    names = [before / n for n in (
        "deploy.log", "source-postdeploy-safety.log", "source-clear-boot.log",
        "source-clear-boot-continuation.log", "source-final-read.log")]
    names += [after / n for n in ("source-deploy.log", "source-usb-recovery.log")]
    return {
        "schema": "leshy.wifi_product_boot.blocker.v1", "status": "blocked",
        "two_board_acceptance": False, "test_network_started": False,
        "installed_source_version": boot["version"], "app_elf_sha256": identity,
        "image_sha256": hashlib.sha256((before / "firmware.bin").read_bytes()).hexdigest(),
        "retained_stop": {k: safety[k] for k in (
            "reason", "reset_reason_code", "watchdog_trip_stage",
            "watchdog_triggered_cpu_mask", "watchdog_incident_sequence",
            "watchdog_journal_nvs_verified", "watchdog_journal_sd_write_attempted",
            "runtime_owner", "lease_mask", "buzzer_inactive", "nrf_ce_inactive")},
        "observed_sd_retry_attempts": attempts,
        "followup_app_elf_sha256": app_elf_sha256(after / "firmware.bin"),
        "followup_image_sha256": hashlib.sha256((after / "firmware.bin").read_bytes()).hexdigest(),
        "followup_written": False, "receiver_unchanged_version": "1.0.0-dev.385",
        "cause": "unconfirmed: startup Task-WDT; later SD retries and unresponsive USB",
        "limits": "Follow-up adds startup-stage logging and a completed-recovery feed; neither its boot nor the AP role is physically accepted. No new feature/cadence credit.",
        "private_log_sha256": {str(p.parent.name + "/" + p.name):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in names},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--timeout-run", type=Path)
    parser.add_argument("--deploy-log", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.timeout_run and args.deploy_log and not (args.before or args.after):
        result = retain_console_timeout(args.timeout_run, args.deploy_log)
    elif args.before and args.after and not (args.timeout_run or args.deploy_log):
        result = retain(args.before, args.after)
    else: parser.error('use --before/--after or --timeout-run/--deploy-log')
    with args.output.open("x") as output:
        output.write(json.dumps(result, indent=2) + "\n")
    print("retained blocked deployment; no HIL acceptance")
