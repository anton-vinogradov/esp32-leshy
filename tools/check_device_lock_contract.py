#!/usr/bin/env python3
"""Fail closed unless CAP-052 Device Lock keeps its security boundaries."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CORE_H = ROOT / "firmware/leshy1/src/services/security/DeviceLock.h"
CORE_CPP = ROOT / "firmware/leshy1/src/services/security/DeviceLock.cpp"
RECORD_H = ROOT / "firmware/leshy1/src/services/security/DeviceLockRecord.h"
RECORD_CPP = ROOT / "firmware/leshy1/src/services/security/DeviceLockRecord.cpp"
PLATFORM = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoDeviceLockSecurity.cpp"
TESTS = ROOT / "tests/native/device_lock_tests.cpp"
CONTROLLER_H = ROOT / "firmware/leshy1/src/apps/device/DeviceLockController.h"
CONTROLLER_CPP = ROOT / "firmware/leshy1/src/apps/device/DeviceLockController.cpp"
CONTROLLER_TESTS = ROOT / "tests/native/device_lock_controller_tests.cpp"
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
PERSISTENCE_RUNNER = ROOT / "tools/run_1x_device_lock_persistence_hil.py"


def require(text: str, marker: str, label: str, failures: list[str]) -> None:
    if marker not in text:
        failures.append(f"missing {label}: {marker}")


def main() -> int:
    core_h = CORE_H.read_text(encoding="utf-8")
    core = CORE_CPP.read_text(encoding="utf-8")
    record_h = RECORD_H.read_text(encoding="utf-8")
    record = RECORD_CPP.read_text(encoding="utf-8")
    platform = PLATFORM.read_text(encoding="utf-8")
    tests = TESTS.read_text(encoding="utf-8")
    controller_h = CONTROLLER_H.read_text(encoding="utf-8")
    controller = CONTROLLER_CPP.read_text(encoding="utf-8")
    controller_tests = CONTROLLER_TESTS.read_text(encoding="utf-8")
    entry = ENTRY.read_text(encoding="utf-8")
    persistence_runner = PERSISTENCE_RUNNER.read_text(encoding="utf-8")
    failures: list[str] = []

    for marker, label in (
        ("kDeviceLockMinimumPinDigits = 6", "six-digit minimum"),
        ("kDeviceLockMaximumPinDigits = 12", "bounded PIN input"),
        ("kDeviceLockPbkdf2Iterations = 120000", "pinned KDF cost"),
        ("kDeviceLockMaximumFailures = 5", "bounded attempts"),
        ("RecoveryOnly,", "recovery-only terminal state"),
        ("ProtectedEvidence,", "evidence gate"),
        ("SecretRead,", "secret gate"),
        ("Export,", "export gate"),
        ("Backup,", "backup gate"),
        ("Companion,", "companion gate"),
        ("SensitiveSettings,", "settings gate"),
        ("SafeStop,", "safe Stop bypass"),
        ("Panic,", "panic bypass"),
        ("Cleanup,", "cleanup bypass"),
        ("UpdateRecovery,", "update/recovery bypass"),
        ("FactoryReset,", "factory-reset bypass"),
        ("eraseProtectedData()", "destructive recovery eraser"),
        ("clearCredentialAndLatch()", "credential/latch cleanup"),
    ):
        require(core_h, marker, label, failures)

    for marker, label in (
        ("constantTimeEqual", "constant-time verifier comparison"),
        ("secureClear(derived.data(), derived.size())",
         "derived verifier zeroization"),
        ("store_.save(credential_)", "persistent retry accounting"),
        ("enterLockedForCredential(nowUs)", "post-persistence backoff"),
        ("failedAttempts >= kDeviceLockMaximumFailures",
         "recovery-only admission"),
        ("DeviceLockAccess::SetupRequired", "fail-closed virgin access"),
        ("operationAlwaysAvailable(operation)", "safe operation bypass"),
        ("eraser.eraseProtectedData()", "erase protected data first"),
        ("store_.clearCredentialAndLatch()", "clear credential second"),
        ("prepareSystemBoundary", "system boundary revocation"),
        ("DeviceLockFailure::ClockRollback", "clock rollback revocation"),
    ):
        require(core, marker, label, failures)

    erase = core.find("eraser.eraseProtectedData()")
    clear = core.find("store_.clearCredentialAndLatch()", erase)
    if erase < 0 or clear < 0 or erase >= clear:
        failures.append("factory reset does not erase protected data before credential")

    for forbidden in ("std::string", "String ", "printf", "Serial",
                      "credentialForPersistenceTest"):
        if forbidden in core_h or forbidden in core:
            failures.append(f"Device Lock core may retain/log PIN material: {forbidden}")

    for marker, label in (
        ("kDeviceLockRecordBytes = 68", "fixed record size"),
        ("encodeDeviceLockRecord", "versioned record encoder"),
        ("decodeDeviceLockRecord", "versioned record decoder"),
        ("crc32(output->data(), 64U)", "record CRC"),
        ("input[6] != 0 || input[7] != 0", "reserved-byte rejection"),
    ):
        require(record_h + record, marker, label, failures)

    for marker, label in (
        ("esp_fill_random(output, size)", "hardware RNG salt"),
        ("mbedtls_md_hmac_reset", "cooperative PBKDF2 implementation"),
        ("MBEDTLS_MD_SHA256", "SHA-256 KDF"),
        ("kDeviceLockKdfYieldInterval = 256", "KDF watchdog yield bound"),
        ("vTaskDelay(1)", "KDF idle-task scheduling point"),
        ("credential.v1", "versioned NVS credential"),
        ("enrolled.v1", "separate provisioned latch"),
        ("nvs_set_blob(storage.get(), kCredentialKey", "credential write"),
        ("nvs_set_u32(storage.get(), kProvisionedLatchKey", "latch write"),
        ("eraseKeyIfPresent(storage.get(), kCredentialKey)",
         "credential erase"),
        ("eraseKeyIfPresent(storage.get(), kProvisionedLatchKey)",
         "latch erase"),
        ("nvs_commit(storage.get())", "durable NVS boundaries"),
        ("DeviceLockLoadStatus::MissingExpected", "missing record fail closed"),
    ):
        require(platform, marker, label, failures)

    save_record = platform.find("nvs_set_blob(storage.get(), kCredentialKey")
    save_latch = platform.find("nvs_set_u32(storage.get(), kProvisionedLatchKey")
    erase_record = platform.find(
        "eraseKeyIfPresent(storage.get(), kCredentialKey)")
    erase_latch = platform.find(
        "eraseKeyIfPresent(storage.get(), kProvisionedLatchKey)")
    if save_record < 0 or save_latch < 0 or save_record >= save_latch:
        failures.append("provisioning latch can publish before credential")
    if erase_record < 0 or erase_latch < 0 or erase_record >= erase_latch:
        failures.append("credential/latch erase order is not fail closed")

    for marker, label in (
        ("testPinPolicyAndSetupRequiredDefault", "default access matrix"),
        ("testWrongPinPersistsBackoffAcrossResetAndEndsRecoveryOnly",
         "persistent retry/recovery test"),
        ("testSuccessfulUnlockClearsPersistentFailuresOnlyAfterSave",
         "successful unlock persistence test"),
        ("testTimeoutClockRollbackAndSystemBoundaryRevoke",
         "volatile unlock revocation test"),
        ("testDestructiveRecoveryOrderingAndFailures",
         "destructive recovery negatives"),
        ("retryRemainingUs == retryRemaining",
         "cancelled recovery preserves retry delay"),
        ("testCorruptOrMissingExpectedCredentialFailsClosed",
         "corrupt/missing fail-closed test"),
        ("testCredentialRecordIsVersionedExactAndCorruptionDetecting",
         "record corruption test"),
    ):
        require(tests, marker, label, failures)

    for marker, label in (
        ("kProductPinDigits =", "fixed legible product PIN shape"),
        ("void DeviceLockSubmission::clear()", "worker submission wipe"),
        ("secureClear(pin_.data(), pin_.size())", "editor PIN wipe"),
        ("secureClear(firstPin_.data(), firstPin_.size())",
         "confirmation PIN wipe"),
        ("DeviceLock::pinWeak", "weak product PIN rejection"),
        ("std::memcmp(firstPin_.data(), pin_.data()",
         "setup confirmation"),
        ("submission_.clear();", "single-use product submission"),
    ):
        require(controller_h + controller, marker, label, failures)

    for marker, label in (
        ("DeviceLockTitle", "Device Lock product page"),
        ("DeviceLockController deviceLockController", "product controller"),
        ("xQueueCreate(", "bounded KDF completion queue"),
        ("xTaskCreatePinnedToCore(", "background KDF task"),
        ("deviceLockWorkerRequest.clear()", "worker PIN wipe"),
        ("deviceLock.completeBlockingOperation(startedUs, finishedUs)",
         "post-KDF retry and unlock timing boundary"),
        ("renderDeviceLockPinCells();", "local PIN cell repaint"),
        ("renderInteractiveScreen(!lastUiActionUsedIncrementalRender)",
         "touch incremental repaint"),
        ("deviceLock.recordActivity(nowUs)", "unlock activity timeout"),
        ("DeviceLockWorkerMode::KdfBenchmark", "non-persistent KDF HIL"),
        ("device-lock.kdf-benchmark confirm-no-persist",
         "explicit KDF HIL command"),
        ("persistence_touched_by_benchmark\\\":false",
         "KDF HIL non-persistence report"),
        ("volatile char* pinBytes", "KDF vector PIN wipe"),
        ("volatile std::uint8_t* verifierBytes",
         "KDF vector verifier wipe"),
        ("benchmark_vector_verified", "exact PBKDF2 HIL vector report"),
    ):
        require(entry, marker, label, failures)

    for marker, label in (
        ("NVS_OFFSET = 0x9000", "exact NVS transaction boundary"),
        ("two independent NVS backup reads differ", "double-read backup"),
        ("restore_flash(", "verified NVS restoration"),
        ("wipe_pin(correct_pin)", "ephemeral correct PIN wipe"),
        ("wipe_pin(wrong_pin)", "ephemeral wrong PIN wipe"),
        ("pin_or_digest_retained\": False", "PIN evidence exclusion"),
        ("private_nvs_in_public_manifest\": False",
         "private NVS evidence exclusion"),
        ("mac_wifi\": False", "Mac Wi-Fi exclusion"),
        ("clone\": False", "clone exclusion"),
        ("cardputer\": False", "Cardputer exclusion"),
    ):
        require(persistence_runner, marker, label, failures)

    for marker, label in (
        ("testConfigureRequiresStrongMatchingConfirmationAndClearsSubmission",
         "setup/confirmation UI test"),
        ("testWeakAndMismatchedPinNeverProduceSubmission",
         "weak/mismatch UI negative test"),
        ("testUnlockCancelRetryAndImmediateLockIntent",
         "unlock/cancel/retry/lock UI test"),
    ):
        require(controller_tests, marker, label, failures)

    if failures:
        print("Device Lock contract failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "Device Lock contract passed: PBKDF2 verifier, persistent bounded retry, "
        "locked access matrix, non-bypassable safe operations, destructive-only recovery, "
        "background product UI and local repaint"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
