#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::services::security {

constexpr std::size_t kDeviceLockMinimumPinDigits = 6;
constexpr std::size_t kDeviceLockMaximumPinDigits = 12;
constexpr std::size_t kDeviceLockSaltBytes = 16;
constexpr std::size_t kDeviceLockVerifierBytes = 32;
constexpr std::size_t kDeviceLockDataKeyBytes = 32;
constexpr std::size_t kDeviceLockWrappingKeyBytes = 32;
constexpr std::size_t kDeviceLockWrapNonceBytes = 12;
constexpr std::size_t kDeviceLockAuthTagBytes = 16;
constexpr std::uint32_t kDeviceLockPbkdf2Iterations = 120000;
constexpr std::uint8_t kDeviceLockMaximumFailures = 5;
constexpr std::uint64_t kDeviceLockIdleTimeoutUs =
    10ULL * 60ULL * 1000000ULL;
constexpr std::uint64_t kDeviceLockMaximumLifetimeUs =
    30ULL * 60ULL * 1000000ULL;

enum class DeviceLockState : std::uint8_t {
    Unconfigured,
    Locked,
    RetryDelay,
    RecoveryOnly,
    Unlocked,
    Fault,
};

enum class DeviceLockFailure : std::uint8_t {
    None,
    InvalidPin,
    WeakPin,
    NotConfigured,
    AlreadyConfigured,
    WrongPin,
    RetryDelay,
    RecoveryRequired,
    StoreFailure,
    CredentialCorrupt,
    CryptoFailure,
    ClockRollback,
    ConfirmationRequired,
    ProtectedEraseFailed,
};

const char* deviceLockStateName(DeviceLockState state);
const char* deviceLockFailureName(DeviceLockFailure failure);

struct DeviceLockCredential final {
    static constexpr std::uint8_t kSchemaVersion = 2;

    std::uint8_t schemaVersion = kSchemaVersion;
    std::uint8_t failedAttempts = 0;
    std::uint32_t iterations = kDeviceLockPbkdf2Iterations;
    std::uint32_t generation = 0;
    std::array<std::uint8_t, kDeviceLockSaltBytes> salt{};
    std::array<std::uint8_t, kDeviceLockVerifierBytes> verifier{};
    std::array<std::uint8_t, kDeviceLockWrapNonceBytes> wrapNonce{};
    std::array<std::uint8_t, kDeviceLockDataKeyBytes> wrappedDataKey{};
    std::array<std::uint8_t, kDeviceLockAuthTagBytes> wrapTag{};

    bool valid() const;
    void clear();
};

enum class DeviceLockLoadStatus : std::uint8_t {
    MissingVirgin,
    MissingExpected,
    Loaded,
    Corrupt,
    Error,
};

enum class DeviceLockBootstrapStatus : std::uint8_t {
    Missing,
    Loaded,
    Corrupt,
    Error,
};

class DeviceLockStore {
public:
    virtual ~DeviceLockStore() = default;
    virtual DeviceLockLoadStatus load(DeviceLockCredential* output) = 0;
    virtual bool save(const DeviceLockCredential& credential) = 0;
    virtual DeviceLockBootstrapStatus loadBootstrapDataKey(
        std::array<std::uint8_t, kDeviceLockDataKeyBytes>* output) = 0;
    virtual bool saveBootstrapDataKey(
        const std::array<std::uint8_t, kDeviceLockDataKeyBytes>& key) = 0;
    virtual bool clearBootstrapDataKey() = 0;
    // Factory reset must remove the credential first and its provisioned latch
    // last. A power loss between those steps therefore restores fail closed as
    // MissingExpected rather than silently returning to a virgin device.
    virtual bool clearCredentialAndLatch() = 0;
};

class DeviceLockCrypto {
public:
    virtual ~DeviceLockCrypto() = default;
    virtual bool fillRandom(std::uint8_t* output, std::size_t size) = 0;
    virtual bool deriveVerifier(
        const char* pin, std::size_t pinLength,
        const std::array<std::uint8_t, kDeviceLockSaltBytes>& salt,
        std::uint32_t iterations,
        std::array<std::uint8_t, kDeviceLockVerifierBytes>* output) = 0;
    virtual bool deriveCredentialKeys(
        const char* pin, std::size_t pinLength,
        const std::array<std::uint8_t, kDeviceLockSaltBytes>& salt,
        std::uint32_t iterations,
        std::array<std::uint8_t, kDeviceLockVerifierBytes>* verifier,
        std::array<std::uint8_t, kDeviceLockWrappingKeyBytes>* wrappingKey) = 0;
    virtual bool wrapDataKey(
        const std::array<std::uint8_t, kDeviceLockWrappingKeyBytes>& wrappingKey,
        const std::array<std::uint8_t, kDeviceLockWrapNonceBytes>& nonce,
        const std::array<std::uint8_t, kDeviceLockDataKeyBytes>& dataKey,
        std::array<std::uint8_t, kDeviceLockDataKeyBytes>* wrappedDataKey,
        std::array<std::uint8_t, kDeviceLockAuthTagBytes>* tag) = 0;
    virtual bool unwrapDataKey(
        const std::array<std::uint8_t, kDeviceLockWrappingKeyBytes>& wrappingKey,
        const std::array<std::uint8_t, kDeviceLockWrapNonceBytes>& nonce,
        const std::array<std::uint8_t, kDeviceLockDataKeyBytes>& wrappedDataKey,
        const std::array<std::uint8_t, kDeviceLockAuthTagBytes>& tag,
        std::array<std::uint8_t, kDeviceLockDataKeyBytes>* dataKey) = 0;
};

class DeviceLockProtectedDataEraser {
public:
    virtual ~DeviceLockProtectedDataEraser() = default;
    virtual bool eraseProtectedData() = 0;
};

enum class DeviceLockOperation : std::uint8_t {
    Status,
    Configure,
    Unlock,
    Lock,
    ProtectedUi,
    ProtectedEvidence,
    SecretRead,
    Export,
    Backup,
    Companion,
    SensitiveSettings,
    SafeStop,
    Panic,
    Cleanup,
    UpdateRecovery,
    FactoryReset,
};

enum class DeviceLockAccess : std::uint8_t {
    Allowed,
    SetupRequired,
    Locked,
    RetryDelayed,
    RecoveryRequired,
    Faulted,
};

const char* deviceLockOperationName(DeviceLockOperation operation);
const char* deviceLockAccessName(DeviceLockAccess access);

struct DeviceLockAudit final {
    DeviceLockState state = DeviceLockState::Unconfigured;
    DeviceLockFailure lastFailure = DeviceLockFailure::None;
    std::uint8_t failedAttempts = 0;
    std::uint32_t credentialGeneration = 0;
    std::uint64_t retryRemainingUs = 0;
    bool protectedAccessAllowed = false;
    bool dataKeyAvailable = false;
};

class DeviceLock final {
public:
    DeviceLock(DeviceLockStore& store, DeviceLockCrypto& crypto)
        : store_(store), crypto_(crypto) {}

    bool restore(std::uint64_t nowUs);
    bool configure(const char* pin, std::size_t pinLength,
                   std::uint64_t nowUs);
    bool unlock(const char* pin, std::size_t pinLength,
                std::uint64_t nowUs);
    // configure()/unlock() timestamp their state before the synchronous
    // verifier runs. A production caller that executes a blocking verifier
    // must immediately shift retry/session deadlines to the actual completion
    // boundary so KDF time cannot consume either security interval.
    bool completeBlockingOperation(std::uint64_t startedUs,
                                   std::uint64_t finishedUs);
    void lock();
    bool recordActivity(std::uint64_t nowUs);
    bool service(std::uint64_t nowUs);

    DeviceLockAccess access(DeviceLockOperation operation,
                            std::uint64_t nowUs);

    // Recovery never unlocks protected content. It first erases every protected
    // object and only then clears the credential/latch. A partial failure stays
    // locked and exposes only another destructive recovery attempt.
    bool factoryReset(bool confirmed,
                      DeviceLockProtectedDataEraser& eraser);

    // Update/recovery, reset and watchdog boundaries revoke the volatile unlock
    // session without modifying the persisted retry counter.
    void prepareSystemBoundary();

    DeviceLockState state() const { return state_; }
    DeviceLockFailure lastFailure() const { return lastFailure_; }
    DeviceLockAudit audit(std::uint64_t nowUs) const;
    bool copyDataKey(
        std::array<std::uint8_t, kDeviceLockDataKeyBytes>* output) const;

    static bool pinValid(const char* pin, std::size_t pinLength);
    static bool pinWeak(const char* pin, std::size_t pinLength);
    static std::uint64_t retryDelayUs(std::uint8_t failedAttempts);
    static bool operationAlwaysAvailable(DeviceLockOperation operation);

private:
    bool persistFailure(std::uint64_t nowUs);
    bool deriveCredentialKeys(
        const char* pin, std::size_t pinLength,
        std::array<std::uint8_t, kDeviceLockVerifierBytes>* verifier,
        std::array<std::uint8_t, kDeviceLockWrappingKeyBytes>* wrappingKey);
    bool provisionBootstrapDataKey();
    void enterLockedForCredential(std::uint64_t nowUs);
    void clearUnlockSession();
    static bool constantTimeEqual(
        const std::array<std::uint8_t, kDeviceLockVerifierBytes>& left,
        const std::array<std::uint8_t, kDeviceLockVerifierBytes>& right);
    static void secureClear(std::uint8_t* bytes, std::size_t size);

    DeviceLockStore& store_;
    DeviceLockCrypto& crypto_;
    DeviceLockCredential credential_{};
    DeviceLockState state_ = DeviceLockState::Unconfigured;
    DeviceLockFailure lastFailure_ = DeviceLockFailure::None;
    std::uint64_t retryUntilUs_ = 0;
    std::uint64_t unlockedAtUs_ = 0;
    std::uint64_t lastActivityUs_ = 0;
    std::array<std::uint8_t, kDeviceLockDataKeyBytes> dataKey_{};
    bool dataKeyAvailable_ = false;
};

}  // namespace leshy1::services::security
