#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>

#include "services/security/DeviceLock.h"
#include "services/security/DeviceLockRecord.h"

using namespace leshy1::services::security;

namespace {

int failures = 0;

#define CHECK(expression)                                                        \
    do {                                                                         \
        if (!(expression)) {                                                     \
            std::cerr << __FILE__ << ':' << __LINE__                             \
                      << ": check failed: " #expression << '\n';               \
            ++failures;                                                          \
        }                                                                        \
    } while (false)

class FakeCrypto final : public DeviceLockCrypto {
public:
    bool fillRandom(std::uint8_t* output, std::size_t size) override {
        ++randomCalls;
        if (fail || output == nullptr) return false;
        for (std::size_t index = 0; index < size; ++index) {
            output[index] = static_cast<std::uint8_t>(0x41U + index);
        }
        return true;
    }

    bool deriveVerifier(
        const char* pin, std::size_t pinLength,
        const std::array<std::uint8_t, kDeviceLockSaltBytes>& salt,
        std::uint32_t iterations,
        std::array<std::uint8_t, kDeviceLockVerifierBytes>* output) override {
        ++deriveCalls;
        if (fail || pin == nullptr || output == nullptr || pinLength == 0 ||
            iterations != kDeviceLockPbkdf2Iterations) {
            return false;
        }
        for (std::size_t index = 0; index < output->size(); ++index) {
            (*output)[index] = static_cast<std::uint8_t>(
                salt[index % salt.size()] ^
                static_cast<std::uint8_t>(pin[index % pinLength]) ^
                static_cast<std::uint8_t>(index * 13U));
        }
        return true;
    }

    bool fail = false;
    unsigned randomCalls = 0;
    unsigned deriveCalls = 0;
};

class MemoryStore final : public DeviceLockStore {
public:
    DeviceLockLoadStatus load(DeviceLockCredential* output) override {
        ++loads;
        if (loadStatus == DeviceLockLoadStatus::Loaded && output != nullptr) {
            *output = credential;
        }
        return loadStatus;
    }

    bool save(const DeviceLockCredential& value) override {
        ++saves;
        if (failSave) return false;
        credential = value;
        loadStatus = DeviceLockLoadStatus::Loaded;
        return true;
    }

    bool clearCredentialAndLatch() override {
        ++clears;
        if (failClear) return false;
        credential.clear();
        loadStatus = DeviceLockLoadStatus::MissingVirgin;
        return true;
    }

    DeviceLockLoadStatus loadStatus = DeviceLockLoadStatus::MissingVirgin;
    DeviceLockCredential credential{};
    bool failSave = false;
    bool failClear = false;
    unsigned loads = 0;
    unsigned saves = 0;
    unsigned clears = 0;
};

class FakeEraser final : public DeviceLockProtectedDataEraser {
public:
    bool eraseProtectedData() override {
        ++calls;
        return succeed;
    }
    bool succeed = true;
    unsigned calls = 0;
};

void configure(DeviceLock& lock, std::uint64_t nowUs = 100) {
    CHECK(lock.restore(nowUs));
    CHECK(lock.configure("704281", 6, nowUs));
    CHECK(lock.state() == DeviceLockState::Unlocked);
}

void testPinPolicyAndSetupRequiredDefault() {
    MemoryStore store;
    FakeCrypto crypto;
    DeviceLock lock(store, crypto);
    CHECK(lock.restore(10));
    CHECK(lock.state() == DeviceLockState::Unconfigured);
    CHECK(lock.access(DeviceLockOperation::ProtectedEvidence, 10) ==
          DeviceLockAccess::SetupRequired);
    CHECK(lock.access(DeviceLockOperation::Companion, 10) ==
          DeviceLockAccess::SetupRequired);
    CHECK(lock.access(DeviceLockOperation::Configure, 10) ==
          DeviceLockAccess::Allowed);
    CHECK(lock.access(DeviceLockOperation::SafeStop, 10) ==
          DeviceLockAccess::Allowed);
    CHECK(lock.access(DeviceLockOperation::Panic, 10) ==
          DeviceLockAccess::Allowed);
    CHECK(lock.access(DeviceLockOperation::UpdateRecovery, 10) ==
          DeviceLockAccess::Allowed);
    CHECK(lock.access(DeviceLockOperation::FactoryReset, 10) ==
          DeviceLockAccess::Allowed);

    CHECK(!DeviceLock::pinValid(nullptr, 6));
    CHECK(!DeviceLock::pinValid("12345", 5));
    CHECK(!DeviceLock::pinValid("12345x", 6));
    CHECK(DeviceLock::pinValid("704281", 6));
    CHECK(DeviceLock::pinWeak("000000", 6));
    CHECK(DeviceLock::pinWeak("123456", 6));
    CHECK(DeviceLock::pinWeak("654321", 6));
    CHECK(!DeviceLock::pinWeak("704281", 6));
    CHECK(!lock.configure("123456", 6, 10));
    CHECK(lock.lastFailure() == DeviceLockFailure::WeakPin);
    CHECK(store.saves == 0);

    CHECK(lock.configure("704281", 6, 20));
    CHECK(store.saves == 1);
    CHECK(crypto.randomCalls == 1);
    CHECK(crypto.deriveCalls == 1);
    CHECK(store.credential.valid());
    CHECK(lock.access(DeviceLockOperation::ProtectedEvidence, 20) ==
          DeviceLockAccess::Allowed);
}

void testLockRestoreAndCorrectUnlock() {
    MemoryStore store;
    FakeCrypto crypto;
    DeviceLock first(store, crypto);
    configure(first);
    first.prepareSystemBoundary();
    CHECK(first.state() == DeviceLockState::Locked);
    CHECK(first.access(DeviceLockOperation::Export, 101) ==
          DeviceLockAccess::Locked);
    CHECK(first.access(DeviceLockOperation::Cleanup, 101) ==
          DeviceLockAccess::Allowed);

    DeviceLock rebooted(store, crypto);
    CHECK(rebooted.restore(0));
    CHECK(rebooted.state() == DeviceLockState::Locked);
    CHECK(rebooted.unlock("704281", 6, 1));
    CHECK(rebooted.state() == DeviceLockState::Unlocked);
    CHECK(rebooted.access(DeviceLockOperation::Backup, 2) ==
          DeviceLockAccess::Allowed);
    CHECK(store.credential.failedAttempts == 0);
}

void testWrongPinPersistsBackoffAcrossResetAndEndsRecoveryOnly() {
    MemoryStore store;
    FakeCrypto crypto;
    DeviceLock configured(store, crypto);
    configure(configured);
    configured.lock();

    std::uint64_t now = 1000;
    for (std::uint8_t attempt = 1;
         attempt <= kDeviceLockMaximumFailures; ++attempt) {
        DeviceLock current(store, crypto);
        CHECK(current.restore(now));
        if (attempt > 1) {
            CHECK(current.state() == DeviceLockState::RetryDelay);
            const std::uint64_t priorDelay =
                DeviceLock::retryDelayUs(attempt - 1U);
            CHECK(current.service(now + priorDelay));
            now += priorDelay;
        }
        CHECK(!current.unlock("804281", 6, now));
        CHECK(store.credential.failedAttempts == attempt);
        const DeviceLockState expected =
            attempt == kDeviceLockMaximumFailures
                ? DeviceLockState::RecoveryOnly
                : DeviceLockState::RetryDelay;
        CHECK(current.state() == expected);
        CHECK(current.access(DeviceLockOperation::ProtectedUi, now) ==
              (attempt == kDeviceLockMaximumFailures
                   ? DeviceLockAccess::RecoveryRequired
                   : DeviceLockAccess::RetryDelayed));
        CHECK(current.access(DeviceLockOperation::SafeStop, now) ==
              DeviceLockAccess::Allowed);
        now += 10;
    }
    CHECK(store.credential.failedAttempts == kDeviceLockMaximumFailures);
    DeviceLock recovered(store, crypto);
    CHECK(recovered.restore(now));
    CHECK(recovered.state() == DeviceLockState::RecoveryOnly);
    CHECK(recovered.access(DeviceLockOperation::Unlock, now) ==
          DeviceLockAccess::RecoveryRequired);
    CHECK(recovered.access(DeviceLockOperation::UpdateRecovery, now) ==
          DeviceLockAccess::Allowed);
    FakeEraser eraser;
    CHECK(!recovered.factoryReset(false, eraser));
    CHECK(recovered.state() == DeviceLockState::RecoveryOnly);
    CHECK(eraser.calls == 0);
}

void testSuccessfulUnlockClearsPersistentFailuresOnlyAfterSave() {
    MemoryStore store;
    FakeCrypto crypto;
    DeviceLock lock(store, crypto);
    configure(lock);
    lock.lock();
    CHECK(!lock.unlock("804281", 6, 1000));
    CHECK(lock.service(1000 + DeviceLock::retryDelayUs(1)));
    const unsigned beforeSuccess = store.saves;
    CHECK(lock.unlock("704281", 6, 7000000));
    CHECK(store.saves == beforeSuccess + 1);
    CHECK(store.credential.failedAttempts == 0);

    lock.lock();
    CHECK(!lock.unlock("804281", 6, 8000000));
    CHECK(lock.service(8000000 + DeviceLock::retryDelayUs(1)));
    store.failSave = true;
    CHECK(!lock.unlock("704281", 6, 14000000));
    CHECK(lock.state() == DeviceLockState::Fault);
    CHECK(lock.access(DeviceLockOperation::ProtectedEvidence, 14000000) ==
          DeviceLockAccess::Faulted);
    CHECK(lock.access(DeviceLockOperation::Panic, 14000000) ==
          DeviceLockAccess::Allowed);
}

void testTimeoutClockRollbackAndSystemBoundaryRevoke() {
    MemoryStore store;
    FakeCrypto crypto;
    DeviceLock lock(store, crypto);
    configure(lock, 100);
    CHECK(lock.recordActivity(200));
    CHECK(lock.service(150));
    CHECK(lock.state() == DeviceLockState::Locked);
    CHECK(lock.lastFailure() == DeviceLockFailure::ClockRollback);
    CHECK(lock.unlock("704281", 6, 300));
    CHECK(lock.service(300 + kDeviceLockIdleTimeoutUs));
    CHECK(lock.state() == DeviceLockState::Locked);
    CHECK(lock.unlock("704281", 6, 400 + kDeviceLockIdleTimeoutUs));
    std::uint64_t now = 400 + kDeviceLockIdleTimeoutUs;
    while (now < 400 + kDeviceLockIdleTimeoutUs +
           kDeviceLockMaximumLifetimeUs) {
        now += kDeviceLockIdleTimeoutUs - 1U;
        if (now >= 400 + kDeviceLockIdleTimeoutUs +
            kDeviceLockMaximumLifetimeUs) {
            break;
        }
        CHECK(lock.recordActivity(now));
    }
    CHECK(lock.service(400 + kDeviceLockIdleTimeoutUs +
                       kDeviceLockMaximumLifetimeUs));
    CHECK(lock.state() == DeviceLockState::Locked);
    CHECK(lock.unlock("704281", 6, now + 1));
    lock.prepareSystemBoundary();
    CHECK(lock.state() == DeviceLockState::Locked);
}

void testBlockingVerifierTimeCannotConsumeRetryOrUnlockIntervals() {
    MemoryStore store;
    FakeCrypto crypto;
    DeviceLock lock(store, crypto);
    constexpr std::uint64_t configureStartedUs = 100U;
    constexpr std::uint64_t configureFinishedUs = 7500100U;
    configure(lock, configureStartedUs);
    CHECK(lock.completeBlockingOperation(configureStartedUs,
                                         configureFinishedUs));
    CHECK(!lock.service(configureFinishedUs + kDeviceLockIdleTimeoutUs - 1U));
    CHECK(lock.state() == DeviceLockState::Unlocked);
    CHECK(lock.service(configureFinishedUs + kDeviceLockIdleTimeoutUs));
    CHECK(lock.state() == DeviceLockState::Locked);

    constexpr std::uint64_t wrongStartedUs = 20000000U;
    constexpr std::uint64_t wrongFinishedUs = 27500000U;
    CHECK(!lock.unlock("804281", 6, wrongStartedUs));
    CHECK(lock.completeBlockingOperation(wrongStartedUs, wrongFinishedUs));
    CHECK(lock.audit(wrongFinishedUs).retryRemainingUs ==
          DeviceLock::retryDelayUs(1));
    CHECK(!lock.service(wrongFinishedUs +
                        DeviceLock::retryDelayUs(1) - 1U));
    CHECK(lock.state() == DeviceLockState::RetryDelay);
    CHECK(lock.service(wrongFinishedUs + DeviceLock::retryDelayUs(1)));
    CHECK(lock.state() == DeviceLockState::Locked);

    constexpr std::uint64_t unlockStartedUs = 40000000U;
    constexpr std::uint64_t unlockFinishedUs = 47500000U;
    CHECK(lock.unlock("704281", 6, unlockStartedUs));
    CHECK(lock.completeBlockingOperation(unlockStartedUs, unlockFinishedUs));
    CHECK(!lock.service(unlockFinishedUs + kDeviceLockIdleTimeoutUs - 1U));
    CHECK(lock.state() == DeviceLockState::Unlocked);
    CHECK(lock.service(unlockFinishedUs + kDeviceLockIdleTimeoutUs));
    CHECK(lock.state() == DeviceLockState::Locked);
}

void testDestructiveRecoveryOrderingAndFailures() {
    MemoryStore store;
    FakeCrypto crypto;
    DeviceLock lock(store, crypto);
    configure(lock);
    lock.lock();
    FakeEraser eraser;
    CHECK(!lock.factoryReset(false, eraser));
    CHECK(eraser.calls == 0);
    CHECK(store.clears == 0);
    CHECK(lock.state() == DeviceLockState::Locked);

    CHECK(!lock.unlock("804281", 6, 1000));
    const std::uint64_t retryRemaining = lock.audit(1001).retryRemainingUs;
    CHECK(retryRemaining != 0);
    CHECK(!lock.factoryReset(false, eraser));
    CHECK(lock.state() == DeviceLockState::RetryDelay);
    CHECK(lock.audit(1001).retryRemainingUs == retryRemaining);
    CHECK(lock.access(DeviceLockOperation::Unlock, 1001) ==
          DeviceLockAccess::RetryDelayed);
    CHECK(lock.service(1000 + DeviceLock::retryDelayUs(1)));

    eraser.succeed = false;
    CHECK(!lock.factoryReset(true, eraser));
    CHECK(store.clears == 0);
    CHECK(lock.state() == DeviceLockState::Fault);
    CHECK(lock.access(DeviceLockOperation::SafeStop, 1) ==
          DeviceLockAccess::Allowed);

    eraser.succeed = true;
    store.failClear = true;
    CHECK(!lock.factoryReset(true, eraser));
    CHECK(eraser.calls == 2);
    CHECK(store.clears == 1);
    CHECK(lock.state() == DeviceLockState::Fault);

    store.failClear = false;
    CHECK(lock.factoryReset(true, eraser));
    CHECK(eraser.calls == 3);
    CHECK(store.clears == 2);
    CHECK(lock.state() == DeviceLockState::Unconfigured);
    CHECK(lock.access(DeviceLockOperation::ProtectedEvidence, 1) ==
          DeviceLockAccess::SetupRequired);
}

void testCorruptOrMissingExpectedCredentialFailsClosed() {
    FakeCrypto crypto;
    for (DeviceLockLoadStatus status : {
             DeviceLockLoadStatus::MissingExpected,
             DeviceLockLoadStatus::Corrupt,
             DeviceLockLoadStatus::Error}) {
        MemoryStore store;
        store.loadStatus = status;
        DeviceLock lock(store, crypto);
        CHECK(!lock.restore(0));
        CHECK(lock.state() == DeviceLockState::Fault);
        CHECK(lock.access(DeviceLockOperation::ProtectedEvidence, 0) ==
              DeviceLockAccess::Faulted);
        CHECK(lock.access(DeviceLockOperation::Cleanup, 0) ==
              DeviceLockAccess::Allowed);
        CHECK(lock.access(DeviceLockOperation::FactoryReset, 0) ==
              DeviceLockAccess::Allowed);
    }
}

void testCredentialRecordIsVersionedExactAndCorruptionDetecting() {
    MemoryStore store;
    FakeCrypto crypto;
    DeviceLock lock(store, crypto);
    configure(lock);
    DeviceLockRecord record{};
    CHECK(encodeDeviceLockRecord(store.credential, &record));
    DeviceLockCredential decoded{};
    CHECK(decodeDeviceLockRecord(record, &decoded));
    CHECK(decoded.schemaVersion == DeviceLockCredential::kSchemaVersion);
    CHECK(decoded.iterations == kDeviceLockPbkdf2Iterations);
    CHECK(decoded.generation == 1);
    CHECK(decoded.salt == store.credential.salt);
    CHECK(decoded.verifier == store.credential.verifier);
    for (std::size_t index : {0U, 4U, 8U, 16U, 32U, 64U}) {
        DeviceLockRecord corrupt = record;
        corrupt[index] ^= 0x01U;
        DeviceLockCredential rejected{};
        CHECK(!decodeDeviceLockRecord(corrupt, &rejected));
        CHECK(!rejected.valid());
    }
}

}  // namespace

int main() {
    testPinPolicyAndSetupRequiredDefault();
    testLockRestoreAndCorrectUnlock();
    testWrongPinPersistsBackoffAcrossResetAndEndsRecoveryOnly();
    testSuccessfulUnlockClearsPersistentFailuresOnlyAfterSave();
    testTimeoutClockRollbackAndSystemBoundaryRevoke();
    testBlockingVerifierTimeCannotConsumeRetryOrUnlockIntervals();
    testDestructiveRecoveryOrderingAndFailures();
    testCorruptOrMissingExpectedCredentialFailsClosed();
    testCredentialRecordIsVersionedExactAndCorruptionDetecting();
    if (failures != 0) {
        std::cerr << failures << " device lock checks failed\n";
        return EXIT_FAILURE;
    }
    std::cout << "Device Lock tests passed\n";
    return EXIT_SUCCESS;
}
