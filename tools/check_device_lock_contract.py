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
PROTECTED_ENVELOPE = ROOT / (
    "firmware/leshy1/src/storage/ProtectedFileEnvelope.cpp")
PRODUCT_IO = ROOT / (
    "firmware/leshy1/src/platform/arduino/ArduinoFsSessionStoreIo.cpp")
TESTS = ROOT / "tests/native/device_lock_tests.cpp"
CONTROLLER_H = ROOT / "firmware/leshy1/src/apps/device/DeviceLockController.h"
CONTROLLER_CPP = ROOT / "firmware/leshy1/src/apps/device/DeviceLockController.cpp"
CONTROLLER_TESTS = ROOT / "tests/native/device_lock_controller_tests.cpp"
ENTRY = ROOT / "firmware/leshy1/src/platform/arduino/ArduinoEntry.cpp"
PERSISTENCE_RUNNER = ROOT / "tools/run_1x_device_lock_persistence_hil.py"
RECOVERY_RUNNER = ROOT / (
    "tools/run_1x_device_lock_recovery_admission_hil.py")
RECOVERY_RETAINER = ROOT / (
    "tools/retain_1x_device_lock_recovery_admission_hil.py")
RECOVERY_ACCEPTANCE = ROOT / (
    "tools/check_device_lock_recovery_admission_hil_acceptance.py")


def require(text: str, marker: str, label: str, failures: list[str]) -> None:
    if marker not in text:
        failures.append(f"missing {label}: {marker}")


def main() -> int:
    core_h = CORE_H.read_text(encoding="utf-8")
    core = CORE_CPP.read_text(encoding="utf-8")
    record_h = RECORD_H.read_text(encoding="utf-8")
    record = RECORD_CPP.read_text(encoding="utf-8")
    platform = PLATFORM.read_text(encoding="utf-8")
    protected_envelope = PROTECTED_ENVELOPE.read_text(encoding="utf-8")
    product_io = PRODUCT_IO.read_text(encoding="utf-8")
    tests = TESTS.read_text(encoding="utf-8")
    controller_h = CONTROLLER_H.read_text(encoding="utf-8")
    controller = CONTROLLER_CPP.read_text(encoding="utf-8")
    controller_tests = CONTROLLER_TESTS.read_text(encoding="utf-8")
    entry = ENTRY.read_text(encoding="utf-8")
    persistence_runner = PERSISTENCE_RUNNER.read_text(encoding="utf-8")
    recovery_runner = RECOVERY_RUNNER.read_text(encoding="utf-8")
    recovery_retainer = RECOVERY_RETAINER.read_text(encoding="utf-8")
    recovery_acceptance = RECOVERY_ACCEPTANCE.read_text(encoding="utf-8")
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
        ("disableCredential(", "non-destructive PIN disable store transition"),
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
        ("store_.disableCredential(dataKey_)",
         "PIN disable preserves the current protected-data key"),
        ("state_ = DeviceLockState::Disabled",
         "explicit PIN-disabled access state"),
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
        ("kDeviceLockRecordBytes = 128", "fixed record size"),
        ("encodeDeviceLockRecord", "versioned record encoder"),
        ("decodeDeviceLockRecord", "versioned record decoder"),
        ("crc32(output->data(), 124U)", "record CRC"),
        ("input[6] != 0 || input[7] != 0", "reserved-byte rejection"),
    ):
        require(record_h + record, marker, label, failures)

    for marker, label in (
        ("esp_fill_random(output, size)", "hardware RNG salt"),
        ("mbedtls_md_hmac_reset", "cooperative PBKDF2 implementation"),
        ("kVerifierDomain", "domain-separated verifier"),
        ("kWrappingDomain", "domain-separated wrapping key"),
        ("mbedtls_gcm_crypt_and_tag", "authenticated data-key wrap"),
        ("mbedtls_gcm_auth_decrypt", "authenticated data-key unwrap"),
        ("MBEDTLS_MD_SHA256", "SHA-256 KDF"),
        ("kDeviceLockKdfYieldInterval = 256", "KDF watchdog yield bound"),
        ("vTaskDelay(1)", "KDF idle-task scheduling point"),
        ("credential.v2", "versioned NVS credential"),
        ("enrolled.v1", "separate provisioned latch"),
        ("data-key.v1", "bootstrap data key"),
        ("disabled.v1", "durable PIN-disabled latch"),
        ("NvsDeviceLockStore::disableCredential(",
         "atomic PIN disable transaction"),
        ("nvs_set_blob(storage.get(), kCredentialKey", "credential write"),
        ("nvs_set_u32(storage.get(), kProvisionedLatchKey", "latch write"),
        ("eraseKeyIfPresent(storage.get(), kCredentialKey)",
         "credential erase"),
        ("eraseKeyIfPresent(storage.get(), kProvisionedLatchKey)",
         "latch erase"),
        ("eraseKeyIfPresent(storage.get(), kBootstrapDataKey)",
         "bootstrap key erase"),
        ("nvs_commit(storage.get())", "durable NVS boundaries"),
        ("DeviceLockLoadStatus::MissingExpected", "missing record fail closed"),
        ("kProductNamespace = \"leshy1-lock\"",
         "fixed product namespace"),
        ("kHilFixtureNamespace = \"leshy1-lock-hil\"",
         "isolated HIL namespace"),
        ("useHilFixtureNamespace(bool enabled)",
         "explicit fixture namespace selection"),
        ("hilFixtureStatePresent() const",
         "stale fixture detection after reboot"),
    ):
        require(platform, marker, label, failures)

    for marker, label in (
        ("kProtectedFileChunkBytes", "bounded encrypted chunks"),
        ("protectedFilePhysicalSize", "exact encrypted size"),
        ("buildProtectedFileChunkNonce", "unique per-chunk nonce"),
        ("buildProtectedFileChunkAad", "path and chunk binding"),
        ("crc32(output->data(), 28U)", "envelope header corruption check"),
        ("protectedCipher_->seal", "product file encryption"),
        ("protectedCipher_->open", "product file authentication"),
        ("deviceLock_->copyDataKey", "volatile key gate"),
        ("secureClear(output, produced)", "auth failure plaintext wipe"),
        ("if (productRoot_) return writeProtectedFile", "all product writes"),
        ("return readProtectedFile(path", "all product reads"),
        ("inspectProtectedFile", "physical encrypted-file inspection"),
        ("/enc-", "physically disjoint encrypted namespace"),
    ):
        require(protected_envelope + product_io, marker, label, failures)

    if entry.count("&protectedDataCipher, &deviceLock") != 7:
        failures.append(
            "every product SD adapter must share the protected cipher/key gate")

    for marker, label in (
        ("leshy.storage.product_bootstrap.v2",
         "physical encrypted bootstrap evidence"),
        ("encrypted_namespace\\\":%s", "encrypted namespace report"),
        ("envelope_header_valid\\\":%s", "envelope header report"),
        ("physical_size_exact\\\":%s", "physical size report"),
        ("ciphertext_differs\\\":%s", "ciphertext/plaintext separation"),
        ("protectedFileInspected", "physical inspection acceptance gate"),
        ("const auto supervisedCheckpoint = []()",
         "bounded product-bootstrap watchdog checkpoint"),
        ("sdSessionStoreIoWorkspace,\n"
         "                               supervisedCheckpoint,",
         "encrypted chunk watchdog callback"),
    ):
        require(entry, marker, label, failures)

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

    disable = platform.find("NvsDeviceLockStore::disableCredential(")
    disable_latch = platform.find(
        "nvs_set_u32(storage.get(), kDisabledLatchKey", disable)
    disable_key = platform.find(
        "nvs_set_blob(storage.get(), kBootstrapDataKey", disable)
    disable_record = platform.find(
        "eraseKeyIfPresent(storage.get(), kCredentialKey)", disable)
    disable_enrolled = platform.find(
        "eraseKeyIfPresent(storage.get(), kProvisionedLatchKey)", disable)
    if not (0 <= disable < disable_latch < disable_key < disable_record <
            disable_enrolled):
        failures.append("PIN disable transaction is not ordered fail closed")

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
        ("testDisablePreservesDataKeyAndAllowsReenrollment",
         "non-destructive PIN disable and cold restore test"),
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
        ("ConfirmDisable", "separate PIN disable confirmation"),
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
        ("DeviceLockDisableAction", "visible PIN disable action"),
        ("device_lock_disable_confirmation",
         "explicit product PIN disable confirmation"),
        ("DeviceLockWorkerMode::KdfBenchmark", "non-persistent KDF HIL"),
        ("device-lock.kdf-benchmark confirm-no-persist",
         "explicit KDF HIL command"),
        ("persistence_touched_by_benchmark\\\":false",
         "KDF HIL non-persistence report"),
        ("volatile char* pinBytes", "KDF vector PIN wipe"),
        ("volatile std::uint8_t* verifierBytes",
         "KDF vector verifier wipe"),
        ("benchmark_vector_verified", "exact PBKDF2 HIL vector report"),
        ("device-lock.persistence-fixture ",
         "HIL-gated persistence fixture command"),
        ("device-lock.protected-read-fixture ",
         "RAM-only protected companion read fixture"),
        ("companion_read_only\\\":true",
         "read fixture excludes companion mutation"),
        ("mutation_scope_allowed\\\":false",
         "read fixture reports denied mutation scope"),
        ("deviceLockProtectedReadHilActive && hilSession.active()",
         "read fixture is physically session-bound"),
        ("fixture_cleanup_required",
         "HIL end blocked before fixture cleanup"),
        ("persistence_fixture_cleanup_required",
         "fixture cleanup continuity in state evidence"),
        ("product_namespace_written_or_erased\\\":false",
         "product namespace mutation exclusion"),
        ("whole_nvs_read_or_copied\\\":false",
         "whole-NVS copy exclusion"),
        ("device-lock.admission", "physical admission matrix command"),
        ("renderDeviceLockBlockedPage", "opaque protected UI replacement"),
        ("DeviceLockOperation::ProtectedUi", "root and page UI gate"),
        ("DeviceLockOperation::ProtectedEvidence", "capture persistence gate"),
        ("DeviceLockOperation::Companion", "companion data gate"),
        ("DeviceLockOperation::SensitiveSettings", "settings gate"),
        ("commandRequiresDeviceLockExport", "console export gate"),
        ("protected_content_returned\\\":false", "no-content denial report"),
        ("factory-reset-preview", "non-destructive reset preview"),
        ("factory-reset-confirm", "confirmed destructive reset"),
        ("credential_present_during_erase", "destructive reset ordering proof"),
    ):
        require(entry, marker, label, failures)

    for marker, label in (
        ("FIXTURE_SCHEMA = \"leshy.device_lock.fixture.v1\"",
         "isolated fixture evidence schema"),
        ("fixture_command(device, \"cleanup\")",
         "explicit fixture cleanup"),
        ("fixture_cleanup_proven", "machine-checked fixture cleanup"),
        ("--reuse-exact-flash", "delta-HIL exact-flash reuse"),
        ("boot_ready_failures(", "Device Lock scoped reboot oracle"),
        ("wipe_pin(correct_pin)", "ephemeral correct PIN wipe"),
        ("wipe_pin(wrong_pin)", "ephemeral wrong PIN wipe"),
        ("pin_or_digest_retained\": False", "PIN evidence exclusion"),
        ("whole_nvs_or_product_namespace_retained\": False",
         "NVS/product namespace evidence exclusion"),
        ("mac_wifi\": False", "Mac Wi-Fi exclusion"),
        ("clone\": False", "clone exclusion"),
        ("cardputer\": False", "Cardputer exclusion"),
    ):
        require(persistence_runner, marker, label, failures)

    for marker, label in (
        ("RUN_SCHEMA = \"leshy.device_lock_recovery_admission_hil.run.v1\"",
         "recovery/admission HIL schema"),
        ("PROTECTED_OPERATIONS", "complete protected operation set"),
        ("SAFE_OPERATIONS", "complete always-available operation set"),
        ("device-lock.admission", "physical admission query"),
        ("factory-reset-preview", "physical reset preview"),
        ("factory-reset-confirm", "physical reset confirmation"),
        ("for attempt in range(1, 6)", "all five physical PIN failures"),
        ("300000", "real five-minute retry bound"),
        ("destructive_order_proven", "machine-checked erase ordering"),
        ("wipe_pin(correct_pin)", "ephemeral correct PIN wipe"),
        ("wipe_pin(wrong_pin)", "ephemeral wrong PIN wipe"),
        ("pin_or_digest_retained\": False", "PIN evidence exclusion"),
        ("mac_wifi\": False", "Mac Wi-Fi exclusion"),
        ("clone\": False", "clone exclusion"),
        ("cardputer\": False", "Cardputer exclusion"),
    ):
        require(recovery_runner, marker, label, failures)

    for marker, label in (
        ("pass_recovery_admission_slice", "retained recovery/admission gate"),
        ("credential_generation_sequence", "exact persisted generations"),
        ("safe_operations_always_allowed", "safe operation acceptance"),
        ("protected_erase_before_credential_clear",
         "destructive ordering acceptance"),
        ("encrypted protected data at rest", "honest remaining boundary"),
    ):
        require(recovery_retainer + recovery_acceptance,
                marker, label, failures)

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
