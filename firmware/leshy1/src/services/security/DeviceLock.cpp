#include "DeviceLock.h"

#include <algorithm>
#include <limits>

namespace leshy1::services::security {
namespace {

bool anyNonzero(const std::uint8_t* bytes, std::size_t size) {
    if (bytes == nullptr) return false;
    std::uint8_t combined = 0;
    for (std::size_t index = 0; index < size; ++index) {
        combined = static_cast<std::uint8_t>(combined | bytes[index]);
    }
    return combined != 0;
}

std::uint64_t saturatingAdd(std::uint64_t left, std::uint64_t right) {
    const std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max();
    return right > maximum - left ? maximum : left + right;
}

}  // namespace

const char* deviceLockStateName(DeviceLockState state) {
    switch (state) {
        case DeviceLockState::Unconfigured: return "unconfigured";
        case DeviceLockState::Disabled: return "disabled";
        case DeviceLockState::Locked: return "locked";
        case DeviceLockState::RetryDelay: return "retry_delay";
        case DeviceLockState::RecoveryOnly: return "recovery_only";
        case DeviceLockState::Unlocked: return "unlocked";
        case DeviceLockState::Fault: return "fault";
    }
    return "fault";
}

const char* deviceLockFailureName(DeviceLockFailure failure) {
    switch (failure) {
        case DeviceLockFailure::None: return "none";
        case DeviceLockFailure::InvalidPin: return "invalid_pin";
        case DeviceLockFailure::WeakPin: return "weak_pin";
        case DeviceLockFailure::NotConfigured: return "not_configured";
        case DeviceLockFailure::AlreadyConfigured: return "already_configured";
        case DeviceLockFailure::WrongPin: return "wrong_pin";
        case DeviceLockFailure::RetryDelay: return "retry_delay";
        case DeviceLockFailure::RecoveryRequired: return "recovery_required";
        case DeviceLockFailure::StoreFailure: return "store_failure";
        case DeviceLockFailure::CredentialCorrupt: return "credential_corrupt";
        case DeviceLockFailure::CryptoFailure: return "crypto_failure";
        case DeviceLockFailure::ClockRollback: return "clock_rollback";
        case DeviceLockFailure::ConfirmationRequired:
            return "confirmation_required";
        case DeviceLockFailure::ProtectedEraseFailed:
            return "protected_erase_failed";
    }
    return "credential_corrupt";
}

const char* deviceLockOperationName(DeviceLockOperation operation) {
    switch (operation) {
        case DeviceLockOperation::Status: return "status";
        case DeviceLockOperation::Configure: return "configure";
        case DeviceLockOperation::Unlock: return "unlock";
        case DeviceLockOperation::Disable: return "disable";
        case DeviceLockOperation::Lock: return "lock";
        case DeviceLockOperation::ProtectedUi: return "protected_ui";
        case DeviceLockOperation::ProtectedEvidence:
            return "protected_evidence";
        case DeviceLockOperation::SecretRead: return "secret_read";
        case DeviceLockOperation::Export: return "export";
        case DeviceLockOperation::Backup: return "backup";
        case DeviceLockOperation::Companion: return "companion";
        case DeviceLockOperation::SensitiveSettings:
            return "sensitive_settings";
        case DeviceLockOperation::SafeStop: return "safe_stop";
        case DeviceLockOperation::Panic: return "panic";
        case DeviceLockOperation::Cleanup: return "cleanup";
        case DeviceLockOperation::UpdateRecovery: return "update_recovery";
        case DeviceLockOperation::FactoryReset: return "factory_reset";
    }
    return "unknown";
}

const char* deviceLockAccessName(DeviceLockAccess access) {
    switch (access) {
        case DeviceLockAccess::Allowed: return "allowed";
        case DeviceLockAccess::SetupRequired: return "setup_required";
        case DeviceLockAccess::Locked: return "locked";
        case DeviceLockAccess::RetryDelayed: return "retry_delayed";
        case DeviceLockAccess::RecoveryRequired: return "recovery_required";
        case DeviceLockAccess::Faulted: return "faulted";
    }
    return "faulted";
}

bool DeviceLockCredential::valid() const {
    return schemaVersion == kSchemaVersion &&
        failedAttempts <= kDeviceLockMaximumFailures &&
        iterations == kDeviceLockPbkdf2Iterations && generation != 0 &&
        anyNonzero(salt.data(), salt.size()) &&
        anyNonzero(verifier.data(), verifier.size()) &&
        anyNonzero(wrapNonce.data(), wrapNonce.size()) &&
        anyNonzero(wrappedDataKey.data(), wrappedDataKey.size()) &&
        anyNonzero(wrapTag.data(), wrapTag.size());
}

void DeviceLockCredential::clear() {
    volatile std::uint8_t* saltCursor = salt.data();
    for (std::size_t index = 0; index < salt.size(); ++index) {
        saltCursor[index] = 0;
    }
    volatile std::uint8_t* verifierCursor = verifier.data();
    for (std::size_t index = 0; index < verifier.size(); ++index) {
        verifierCursor[index] = 0;
    }
    volatile std::uint8_t* nonceCursor = wrapNonce.data();
    for (std::size_t index = 0; index < wrapNonce.size(); ++index) {
        nonceCursor[index] = 0;
    }
    volatile std::uint8_t* wrappedCursor = wrappedDataKey.data();
    for (std::size_t index = 0; index < wrappedDataKey.size(); ++index) {
        wrappedCursor[index] = 0;
    }
    volatile std::uint8_t* tagCursor = wrapTag.data();
    for (std::size_t index = 0; index < wrapTag.size(); ++index) {
        tagCursor[index] = 0;
    }
    schemaVersion = kSchemaVersion;
    failedAttempts = 0;
    iterations = kDeviceLockPbkdf2Iterations;
    generation = 0;
}

bool DeviceLock::pinValid(const char* pin, std::size_t pinLength) {
    if (pin == nullptr || pinLength < kDeviceLockMinimumPinDigits ||
        pinLength > kDeviceLockMaximumPinDigits) {
        return false;
    }
    for (std::size_t index = 0; index < pinLength; ++index) {
        if (pin[index] < '0' || pin[index] > '9') return false;
    }
    return true;
}

bool DeviceLock::pinWeak(const char* pin, std::size_t pinLength) {
    if (!pinValid(pin, pinLength)) return true;
    bool repeated = true;
    bool ascending = true;
    bool descending = true;
    for (std::size_t index = 1; index < pinLength; ++index) {
        repeated = repeated && pin[index] == pin[0];
        ascending = ascending &&
            pin[index] == static_cast<char>('0' +
                ((pin[index - 1U] - '0' + 1) % 10));
        descending = descending &&
            pin[index] == static_cast<char>('0' +
                ((pin[index - 1U] - '0' + 9) % 10));
    }
    return repeated || ascending || descending;
}

std::uint64_t DeviceLock::retryDelayUs(std::uint8_t failedAttempts) {
    switch (failedAttempts) {
        case 0: return 0;
        case 1: return 5ULL * 1000000ULL;
        case 2: return 15ULL * 1000000ULL;
        case 3: return 60ULL * 1000000ULL;
        case 4: return 5ULL * 60ULL * 1000000ULL;
        default: return 0;
    }
}

bool DeviceLock::operationAlwaysAvailable(DeviceLockOperation operation) {
    switch (operation) {
        case DeviceLockOperation::Status:
        case DeviceLockOperation::Lock:
        case DeviceLockOperation::SafeStop:
        case DeviceLockOperation::Panic:
        case DeviceLockOperation::Cleanup:
        case DeviceLockOperation::UpdateRecovery:
        case DeviceLockOperation::FactoryReset:
            return true;
        case DeviceLockOperation::Disable:
            return false;
        default:
            return false;
    }
}

void DeviceLock::secureClear(std::uint8_t* bytes, std::size_t size) {
    volatile std::uint8_t* cursor = bytes;
    while (size-- != 0U) *cursor++ = 0;
}

bool DeviceLock::constantTimeEqual(
    const std::array<std::uint8_t, kDeviceLockVerifierBytes>& left,
    const std::array<std::uint8_t, kDeviceLockVerifierBytes>& right) {
    std::uint8_t difference = 0;
    for (std::size_t index = 0; index < left.size(); ++index) {
        difference = static_cast<std::uint8_t>(
            difference | static_cast<std::uint8_t>(left[index] ^ right[index]));
    }
    return difference == 0;
}

void DeviceLock::clearUnlockSession() {
    unlockedAtUs_ = 0;
    lastActivityUs_ = 0;
    secureClear(dataKey_.data(), dataKey_.size());
    dataKeyAvailable_ = false;
}

void DeviceLock::enterLockedForCredential(std::uint64_t nowUs) {
    clearUnlockSession();
    if (credential_.failedAttempts >= kDeviceLockMaximumFailures) {
        state_ = DeviceLockState::RecoveryOnly;
        retryUntilUs_ = 0;
        lastFailure_ = DeviceLockFailure::RecoveryRequired;
        return;
    }
    const std::uint64_t delay = retryDelayUs(credential_.failedAttempts);
    if (delay == 0) {
        state_ = DeviceLockState::Locked;
        retryUntilUs_ = 0;
    } else {
        state_ = DeviceLockState::RetryDelay;
        retryUntilUs_ = saturatingAdd(nowUs, delay);
        lastFailure_ = DeviceLockFailure::RetryDelay;
    }
}

bool DeviceLock::restore(std::uint64_t nowUs) {
    credential_.clear();
    clearUnlockSession();
    retryUntilUs_ = 0;
    DeviceLockCredential loaded{};
    const DeviceLockLoadStatus status = store_.load(&loaded);
    if (status == DeviceLockLoadStatus::MissingVirgin) {
        if (!provisionBootstrapDataKey()) {
            state_ = DeviceLockState::Fault;
            lastFailure_ = DeviceLockFailure::StoreFailure;
            return false;
        }
        state_ = DeviceLockState::Unconfigured;
        lastFailure_ = DeviceLockFailure::None;
        return true;
    }
    if (status == DeviceLockLoadStatus::Disabled) {
        if (!provisionBootstrapDataKey(false)) {
            state_ = DeviceLockState::Fault;
            lastFailure_ = DeviceLockFailure::StoreFailure;
            return false;
        }
        state_ = DeviceLockState::Disabled;
        lastFailure_ = DeviceLockFailure::None;
        return true;
    }
    if (status != DeviceLockLoadStatus::Loaded || !loaded.valid()) {
        loaded.clear();
        state_ = DeviceLockState::Fault;
        lastFailure_ = status == DeviceLockLoadStatus::Error
            ? DeviceLockFailure::StoreFailure
            : DeviceLockFailure::CredentialCorrupt;
        return false;
    }
    credential_ = loaded;
    loaded.clear();
    std::array<std::uint8_t, kDeviceLockDataKeyBytes> staleBootstrap{};
    const DeviceLockBootstrapStatus bootstrapStatus =
        store_.loadBootstrapDataKey(&staleBootstrap);
    secureClear(staleBootstrap.data(), staleBootstrap.size());
    if (bootstrapStatus == DeviceLockBootstrapStatus::Loaded &&
        !store_.clearBootstrapDataKey()) {
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::StoreFailure;
        return false;
    }
    if (bootstrapStatus == DeviceLockBootstrapStatus::Corrupt ||
        bootstrapStatus == DeviceLockBootstrapStatus::Error) {
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::StoreFailure;
        return false;
    }
    lastFailure_ = DeviceLockFailure::None;
    enterLockedForCredential(nowUs);
    return true;
}

bool DeviceLock::provisionBootstrapDataKey(bool allowCreate) {
    std::array<std::uint8_t, kDeviceLockDataKeyBytes> candidate{};
    const DeviceLockBootstrapStatus status =
        store_.loadBootstrapDataKey(&candidate);
    if (status == DeviceLockBootstrapStatus::Loaded) {
        if (!anyNonzero(candidate.data(), candidate.size())) {
            secureClear(candidate.data(), candidate.size());
            return false;
        }
    } else if (status == DeviceLockBootstrapStatus::Missing && allowCreate) {
        if (!crypto_.fillRandom(candidate.data(), candidate.size()) ||
            !anyNonzero(candidate.data(), candidate.size()) ||
            !store_.saveBootstrapDataKey(candidate)) {
            secureClear(candidate.data(), candidate.size());
            return false;
        }
    } else {
        secureClear(candidate.data(), candidate.size());
        return false;
    }
    dataKey_ = candidate;
    dataKeyAvailable_ = true;
    secureClear(candidate.data(), candidate.size());
    return true;
}

bool DeviceLock::deriveCredentialKeys(
    const char* pin, std::size_t pinLength,
    std::array<std::uint8_t, kDeviceLockVerifierBytes>* verifier,
    std::array<std::uint8_t, kDeviceLockWrappingKeyBytes>* wrappingKey) {
    if (verifier == nullptr || wrappingKey == nullptr) return false;
    verifier->fill(0);
    wrappingKey->fill(0);
    return crypto_.deriveCredentialKeys(
        pin, pinLength, credential_.salt, credential_.iterations,
        verifier, wrappingKey);
}

bool DeviceLock::configure(const char* pin, std::size_t pinLength,
                           std::uint64_t nowUs) {
    if (state_ != DeviceLockState::Unconfigured &&
        state_ != DeviceLockState::Disabled) {
        lastFailure_ = DeviceLockFailure::AlreadyConfigured;
        return false;
    }
    if (!pinValid(pin, pinLength)) {
        lastFailure_ = DeviceLockFailure::InvalidPin;
        return false;
    }
    if (pinWeak(pin, pinLength)) {
        lastFailure_ = DeviceLockFailure::WeakPin;
        return false;
    }

    DeviceLockCredential candidate{};
    candidate.generation = 1;
    std::array<std::uint8_t, kDeviceLockWrappingKeyBytes> wrappingKey{};
    if (!crypto_.fillRandom(candidate.salt.data(), candidate.salt.size()) ||
        !anyNonzero(candidate.salt.data(), candidate.salt.size()) ||
        !dataKeyAvailable_ ||
        !crypto_.deriveCredentialKeys(
            pin, pinLength, candidate.salt, candidate.iterations,
            &candidate.verifier, &wrappingKey) ||
        !crypto_.fillRandom(candidate.wrapNonce.data(),
                            candidate.wrapNonce.size()) ||
        !crypto_.wrapDataKey(wrappingKey, candidate.wrapNonce, dataKey_,
                             &candidate.wrappedDataKey,
                             &candidate.wrapTag) ||
        !candidate.valid()) {
        secureClear(wrappingKey.data(), wrappingKey.size());
        candidate.clear();
        lastFailure_ = DeviceLockFailure::CryptoFailure;
        return false;
    }
    secureClear(wrappingKey.data(), wrappingKey.size());
    if (!store_.save(candidate)) {
        candidate.clear();
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::StoreFailure;
        return false;
    }
    if (!store_.clearBootstrapDataKey()) {
        candidate.clear();
        clearUnlockSession();
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::StoreFailure;
        return false;
    }
    credential_ = candidate;
    candidate.clear();
    state_ = DeviceLockState::Unlocked;
    retryUntilUs_ = 0;
    unlockedAtUs_ = nowUs;
    lastActivityUs_ = nowUs;
    lastFailure_ = DeviceLockFailure::None;
    return true;
}

bool DeviceLock::persistFailure(std::uint64_t nowUs) {
    if (credential_.failedAttempts < kDeviceLockMaximumFailures) {
        ++credential_.failedAttempts;
    }
    if (credential_.generation == std::numeric_limits<std::uint32_t>::max()) {
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::StoreFailure;
        return false;
    }
    ++credential_.generation;
    if (!store_.save(credential_)) {
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::StoreFailure;
        return false;
    }
    enterLockedForCredential(nowUs);
    if (state_ != DeviceLockState::RecoveryOnly) {
        lastFailure_ = DeviceLockFailure::WrongPin;
    }
    return false;
}

bool DeviceLock::unlock(const char* pin, std::size_t pinLength,
                        std::uint64_t nowUs) {
    service(nowUs);
    if (state_ == DeviceLockState::Unconfigured) {
        lastFailure_ = DeviceLockFailure::NotConfigured;
        return false;
    }
    if (state_ == DeviceLockState::RetryDelay) {
        lastFailure_ = DeviceLockFailure::RetryDelay;
        return false;
    }
    if (state_ == DeviceLockState::RecoveryOnly) {
        lastFailure_ = DeviceLockFailure::RecoveryRequired;
        return false;
    }
    if (state_ == DeviceLockState::Fault) return false;
    if (state_ == DeviceLockState::Unlocked) return true;
    if (!pinValid(pin, pinLength)) {
        // Invalid shapes are still counted so callers cannot obtain a free
        // format oracle for an enrolled device.
        return persistFailure(nowUs);
    }

    std::array<std::uint8_t, kDeviceLockVerifierBytes> derived{};
    std::array<std::uint8_t, kDeviceLockWrappingKeyBytes> wrappingKey{};
    if (!deriveCredentialKeys(pin, pinLength, &derived, &wrappingKey)) {
        secureClear(derived.data(), derived.size());
        secureClear(wrappingKey.data(), wrappingKey.size());
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::CryptoFailure;
        return false;
    }
    const bool match = constantTimeEqual(derived, credential_.verifier);
    secureClear(derived.data(), derived.size());
    if (!match) {
        secureClear(wrappingKey.data(), wrappingKey.size());
        return persistFailure(nowUs);
    }

    std::array<std::uint8_t, kDeviceLockDataKeyBytes> unwrapped{};
    if (!crypto_.unwrapDataKey(
            wrappingKey, credential_.wrapNonce, credential_.wrappedDataKey,
            credential_.wrapTag, &unwrapped) ||
        !anyNonzero(unwrapped.data(), unwrapped.size())) {
        secureClear(wrappingKey.data(), wrappingKey.size());
        secureClear(unwrapped.data(), unwrapped.size());
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::CredentialCorrupt;
        return false;
    }
    secureClear(wrappingKey.data(), wrappingKey.size());

    if (credential_.failedAttempts != 0) {
        credential_.failedAttempts = 0;
        if (credential_.generation == std::numeric_limits<std::uint32_t>::max()) {
            state_ = DeviceLockState::Fault;
            lastFailure_ = DeviceLockFailure::StoreFailure;
            return false;
        }
        ++credential_.generation;
        if (!store_.save(credential_)) {
            secureClear(unwrapped.data(), unwrapped.size());
            state_ = DeviceLockState::Fault;
            lastFailure_ = DeviceLockFailure::StoreFailure;
            return false;
        }
    }
    dataKey_ = unwrapped;
    dataKeyAvailable_ = true;
    secureClear(unwrapped.data(), unwrapped.size());
    state_ = DeviceLockState::Unlocked;
    retryUntilUs_ = 0;
    unlockedAtUs_ = nowUs;
    lastActivityUs_ = nowUs;
    lastFailure_ = DeviceLockFailure::None;
    return true;
}

bool DeviceLock::disable(bool confirmed) {
    if (!confirmed) {
        lastFailure_ = DeviceLockFailure::ConfirmationRequired;
        return false;
    }
    if (state_ != DeviceLockState::Unlocked || !dataKeyAvailable_) {
        lastFailure_ = DeviceLockFailure::NotConfigured;
        return false;
    }
    if (!store_.disableCredential(dataKey_)) {
        clearUnlockSession();
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::StoreFailure;
        return false;
    }
    credential_.clear();
    state_ = DeviceLockState::Disabled;
    retryUntilUs_ = 0;
    unlockedAtUs_ = 0;
    lastActivityUs_ = 0;
    lastFailure_ = DeviceLockFailure::None;
    return true;
}

bool DeviceLock::completeBlockingOperation(std::uint64_t startedUs,
                                           std::uint64_t finishedUs) {
    if (finishedUs < startedUs) {
        lock();
        lastFailure_ = DeviceLockFailure::ClockRollback;
        return false;
    }
    const std::uint64_t elapsedUs = finishedUs - startedUs;
    if (state_ == DeviceLockState::RetryDelay) {
        retryUntilUs_ = saturatingAdd(retryUntilUs_, elapsedUs);
    } else if (state_ == DeviceLockState::Unlocked) {
        unlockedAtUs_ = saturatingAdd(unlockedAtUs_, elapsedUs);
        lastActivityUs_ = saturatingAdd(lastActivityUs_, elapsedUs);
    }
    return true;
}

void DeviceLock::lock() {
    // Disabled mode has no volatile unlock session to revoke; its durable
    // bootstrap key intentionally remains available until PIN enrollment.
    if (state_ == DeviceLockState::Disabled) return;
    clearUnlockSession();
    if (credential_.valid()) {
        if (credential_.failedAttempts >= kDeviceLockMaximumFailures) {
            state_ = DeviceLockState::RecoveryOnly;
            retryUntilUs_ = 0;
        } else if (state_ != DeviceLockState::RetryDelay) {
            state_ = DeviceLockState::Locked;
            retryUntilUs_ = 0;
        }
    } else if (state_ != DeviceLockState::Unconfigured &&
               state_ != DeviceLockState::Disabled) {
        state_ = DeviceLockState::Fault;
    }
}

bool DeviceLock::recordActivity(std::uint64_t nowUs) {
    if (state_ != DeviceLockState::Unlocked) return false;
    if (nowUs < unlockedAtUs_ || nowUs < lastActivityUs_) {
        lock();
        lastFailure_ = DeviceLockFailure::ClockRollback;
        return false;
    }
    if (nowUs - unlockedAtUs_ >= kDeviceLockMaximumLifetimeUs ||
        nowUs - lastActivityUs_ >= kDeviceLockIdleTimeoutUs) {
        lock();
        return false;
    }
    lastActivityUs_ = nowUs;
    return true;
}

bool DeviceLock::service(std::uint64_t nowUs) {
    if (state_ == DeviceLockState::RetryDelay && nowUs >= retryUntilUs_) {
        state_ = DeviceLockState::Locked;
        retryUntilUs_ = 0;
        lastFailure_ = DeviceLockFailure::None;
        return true;
    }
    if (state_ != DeviceLockState::Unlocked) return false;
    if (nowUs < unlockedAtUs_ || nowUs < lastActivityUs_) {
        lock();
        lastFailure_ = DeviceLockFailure::ClockRollback;
        return true;
    }
    if (nowUs - unlockedAtUs_ >= kDeviceLockMaximumLifetimeUs ||
        nowUs - lastActivityUs_ >= kDeviceLockIdleTimeoutUs) {
        lock();
        return true;
    }
    return false;
}

DeviceLockAccess DeviceLock::access(DeviceLockOperation operation,
                                    std::uint64_t nowUs) {
    service(nowUs);
    if (operationAlwaysAvailable(operation)) return DeviceLockAccess::Allowed;
    if (operation == DeviceLockOperation::Configure) {
        return state_ == DeviceLockState::Unconfigured ||
                       state_ == DeviceLockState::Disabled
            ? DeviceLockAccess::Allowed : DeviceLockAccess::Locked;
    }
    if (operation == DeviceLockOperation::Unlock) {
        switch (state_) {
            case DeviceLockState::Locked: return DeviceLockAccess::Allowed;
            case DeviceLockState::RetryDelay:
                return DeviceLockAccess::RetryDelayed;
            case DeviceLockState::RecoveryOnly:
                return DeviceLockAccess::RecoveryRequired;
            case DeviceLockState::Fault: return DeviceLockAccess::Faulted;
            case DeviceLockState::Unconfigured:
                return DeviceLockAccess::SetupRequired;
            case DeviceLockState::Disabled:
                return DeviceLockAccess::SetupRequired;
            case DeviceLockState::Unlocked: return DeviceLockAccess::Allowed;
        }
    }
    if (operation == DeviceLockOperation::Disable) {
        if (state_ == DeviceLockState::Unlocked) {
            return DeviceLockAccess::Allowed;
        }
        if (state_ == DeviceLockState::Fault) {
            return DeviceLockAccess::Faulted;
        }
        if (state_ == DeviceLockState::RetryDelay) {
            return DeviceLockAccess::RetryDelayed;
        }
        if (state_ == DeviceLockState::RecoveryOnly) {
            return DeviceLockAccess::RecoveryRequired;
        }
        return state_ == DeviceLockState::Disabled ||
                       state_ == DeviceLockState::Unconfigured
            ? DeviceLockAccess::SetupRequired
            : DeviceLockAccess::Locked;
    }
    switch (state_) {
        case DeviceLockState::Unconfigured:
            return DeviceLockAccess::SetupRequired;
        case DeviceLockState::Disabled:
            return DeviceLockAccess::Allowed;
        case DeviceLockState::Locked:
            return DeviceLockAccess::Locked;
        case DeviceLockState::RetryDelay:
            return DeviceLockAccess::RetryDelayed;
        case DeviceLockState::RecoveryOnly:
            return DeviceLockAccess::RecoveryRequired;
        case DeviceLockState::Unlocked:
            return DeviceLockAccess::Allowed;
        case DeviceLockState::Fault:
            return DeviceLockAccess::Faulted;
    }
    return DeviceLockAccess::Faulted;
}

bool DeviceLock::factoryReset(bool confirmed,
                              DeviceLockProtectedDataEraser& eraser) {
    clearUnlockSession();
    if (!confirmed) {
        lock();
        lastFailure_ = DeviceLockFailure::ConfirmationRequired;
        return false;
    }
    if (!eraser.eraseProtectedData()) {
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::ProtectedEraseFailed;
        return false;
    }
    if (!store_.clearCredentialAndLatch()) {
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::StoreFailure;
        return false;
    }
    credential_.clear();
    if (!provisionBootstrapDataKey()) {
        state_ = DeviceLockState::Fault;
        lastFailure_ = DeviceLockFailure::StoreFailure;
        return false;
    }
    state_ = DeviceLockState::Unconfigured;
    retryUntilUs_ = 0;
    lastFailure_ = DeviceLockFailure::None;
    return true;
}

void DeviceLock::prepareSystemBoundary() {
    lock();
}

DeviceLockAudit DeviceLock::audit(std::uint64_t nowUs) const {
    DeviceLockAudit result{};
    result.state = state_;
    result.lastFailure = lastFailure_;
    result.failedAttempts = credential_.failedAttempts;
    result.credentialGeneration = credential_.generation;
    result.protectedAccessAllowed = state_ == DeviceLockState::Unlocked ||
        state_ == DeviceLockState::Disabled;
    result.dataKeyAvailable = dataKeyAvailable_;
    if (state_ == DeviceLockState::RetryDelay && nowUs < retryUntilUs_) {
        result.retryRemainingUs = retryUntilUs_ - nowUs;
    }
    return result;
}

bool DeviceLock::copyDataKey(
    std::array<std::uint8_t, kDeviceLockDataKeyBytes>* output) const {
    if (output == nullptr || !dataKeyAvailable_ ||
        (state_ != DeviceLockState::Unconfigured &&
         state_ != DeviceLockState::Disabled &&
         state_ != DeviceLockState::Unlocked)) {
        if (output != nullptr) output->fill(0);
        return false;
    }
    *output = dataKey_;
    return true;
}

}  // namespace leshy1::services::security
