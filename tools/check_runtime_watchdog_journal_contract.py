#!/usr/bin/env python3
"""Fail closed unless watchdog evidence survives reset and mirrors safely."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
ADAPTER = ROOT / (
    "firmware/leshy1/src/platform/arduino/BoardRuntimeWatchdogJournal.cpp"
)
CODEC = ROOT / "firmware/leshy1/src/kernel/safety/RuntimeWatchdogJournal.cpp"
CONFIG = ROOT / "firmware/leshy1/platformio.ini"
RUNNER = ROOT / "tools/run_1x_safety_watchdog_hil.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"runtime watchdog journal contract failed: {message}")


def function(text: str, signature: str, next_signature: str) -> str:
    start = text.index(signature)
    end = text.index(next_signature, start)
    return text[start:end]


def main() -> int:
    entry = ENTRY.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")
    codec = CODEC.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")

    isr_record = function(
        entry,
        "bool IRAM_ATTR recordRuntimeSafetyWatchdogTrip(",
        "void IRAM_ATTR ignoreTaskWatchdogMessage",
    )
    require("quiesceEmergencyGpioFromIsr();" in isr_record,
            "ISR must quiesce outputs before retaining evidence")
    require(isr_record.index("quiesceEmergencyGpioFromIsr();") <
            isr_record.index("runtimeWatchdogTraceRtc.magic = 0"),
            "output quiesce must precede RTC diagnostic writes")
    for forbidden in ("Preferences", "f_open", "f_write", "filesystem"):
        require(forbidden not in isr_record,
                f"ISR must not perform flash/filesystem I/O: {forbidden}")
    for token in (
        "runtimeSafetyNextJournalSequence",
        "runtimeWatchdogTraceRtc.journalSequence = journalSequence",
        "runtimeWatchdogTraceRtc.journalSequenceInverse = ~journalSequence",
    ):
        require(token in isr_record,
                f"ISR trace lacks durable incident identity {token!r}")

    setup = entry[entry.index("void setup() {"):]
    persist = setup.index("persistRuntimeWatchdogJournalAtBoot();")
    arm = setup.index("armRuntimeSafetyWatchdog()")
    display = setup.index("display.init()")
    recover = setup.index("recoverProductCatalogAtBoot();")
    mirror = setup.index("mirrorRuntimeWatchdogJournalToSdAtBoot();")
    workers = setup.index("initializeProductSurveyWorker()")
    require(persist < arm < display < recover < mirror < workers,
            "NVS must precede runtime work and SD mirror must precede workers")
    require("if (!safetySupervisor.latched()) {" in setup[:mirror],
            "SD mirror must only run outside latched Safe Mode")

    persist_fn = function(
        entry,
        "void persistRuntimeWatchdogJournalAtBoot()",
        "void mirrorRuntimeWatchdogJournalToSdAtBoot()",
    )
    for token in (
        "sameRuntimeWatchdogIncident(",
        "trace.journalSequence",
        "trace.resetReason",
        '"sequence_mismatch"',
        "runtimeWatchdogJournalStore.save(candidate)",
        '"written_verified"',
        "confirmRuntimeWatchdogJournalCommitted();",
    ):
        require(token in persist_fn, f"missing immediate NVS guard {token!r}")
    require(persist_fn.index("runtimeWatchdogJournalStore.save(candidate)") <
            persist_fn.rindex("confirmRuntimeWatchdogJournalCommitted();"),
            "RTC commit marker must follow verified NVS save")

    mirror_fn = function(
        entry,
        "void mirrorRuntimeWatchdogJournalToSdAtBoot()",
        "void clearRuntimeWatchdogTrace()",
    )
    for token in (
        "productBootRecovery.expectedFingerprint",
        "exactCidFingerprint(",
        "ProhibitedLowVoltage",
        "resourceBroker.acquire(kCrashJournalOwner, required)",
        "policy.identificationOnly = true",
        "runSdIdentificationStateMachine(",
        "filesystem.cachedFreeBytes() < 4096U",
        "runtimeWatchdogJournalStore.writeSd(",
        "filesystem.cleanupComplete()",
        "resourceBroker.releaseAll(kCrashJournalOwner)",
        "saveSdMirroredSequence(",
    ):
        require(token in mirror_fn, f"missing SD admission/cleanup guard {token!r}")

    for token in (
        'constexpr const char* kNamespace = "leshy1-crash"',
        '"/leshy/diagnostics/v1/watchdog-%08lx.json"',
        '"/leshy/diagnostics/v1/watchdog-%08lx.tmp"',
        "new (std::nothrow) SdWriteWorkspace{}",
        "f_sync(&workspace->file)",
        "exactFile(driveNumber, relativeTemporary, json, size, *workspace)",
        "f_rename(fullTemporary, fullFinal)",
        "exactFile(driveNumber, relativeFinal, json, size, *workspace)",
    ):
        require(token in adapter, f"missing atomic SD writer guard {token!r}")

    clear_fn = function(
        entry, "void clearSafetyRetainedRecord()", "void emitSafetyState("
    )
    for forbidden in ("runtimeWatchdogJournalStore", "Preferences", "f_unlink"):
        require(forbidden not in clear_fn,
                f"clearing Safe Mode must retain durable history: {forbidden}")

    for token in (
        '\\"schema\\":\\"leshy.runtime_watchdog.crash.v1\\"',
        '\\"reset_reason_code\\":%lu',
        '\\"stage\\":\\"%s\\"',
        '\\"wifi_view\\":\\"%s\\"',
    ):
        require(token in codec, f"missing privacy-minimal JSON field {token!r}")
    for token in (
        "watchdog_journal_nvs_verified",
        "watchdog_journal_sd_status",
        "watchdog_journal_sd_mirrored_sequence",
    ):
        require(token in entry, f"missing observable state field {token!r}")
    version = re.search(r'LESHY1_VERSION=\\"1\.0\.0-dev\.(\d+)\\"', config)
    require(version is not None and int(version.group(1)) >= 376,
            "candidate version must preserve the dev.376 watchdog journal")
    require("[[gnu::noinline]] bool exactFile" in adapter,
            "SD verification must keep its bounded buffer out of writeSd")
    require("-fno-exceptions" in config,
            "status-return firmware must omit unused exception metadata")
    for token in (
        'RUN_SCHEMA = "leshy.safety_watchdog_hil.run.v2"',
        '"watchdog_journal_persist_status": (',
        '"written_verified" if first_boot else "already_persisted"',
        '"watchdog_journal_sd_status": "written_verified"',
        '"watchdog_journal_sd_mirrored_sequence": expected_sequence',
        "capture_reconnecting_until_ready(",
        '"clear_usb_disconnects"',
        '"git", "status", "--porcelain", "--untracked-files=all"',
    ):
        require(token in runner,
                f"focused exact-source HIL lacks assertion {token!r}")

    print(
        "runtime watchdog journal contract passed: ISR writes RTC only; first "
        "Safe-Mode boot verifies NVS; enrolled exact-CID SD mirror is atomic, "
        "power/resource bounded and preserves history"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
