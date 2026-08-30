#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/automation/AutomationPackage.h"

namespace leshy1::apps::automation {

constexpr std::uint16_t kAutomationTrustSchemaVersion = 1U;
constexpr std::size_t kAutomationTrustMaximumKeys = 4U;
constexpr std::size_t kAutomationP256PublicKeyBytes = 65U;
constexpr std::size_t kAutomationTrustLabelBytes = 24U;
constexpr std::size_t kAutomationTrustRecordBytes = 408U;

struct AutomationTrustedKey final {
    std::array<std::uint8_t, kAutomationKeyIdBytes> keyId{};
    // SEC1 uncompressed P-256 point: 0x04 || X(32) || Y(32).
    std::array<std::uint8_t, kAutomationP256PublicKeyBytes> publicKey{};
    std::array<char, kAutomationTrustLabelBytes + 1U> label{};
};

struct AutomationTrustSnapshot final {
    std::uint16_t schemaVersion = kAutomationTrustSchemaVersion;
    std::uint32_t generation = 0U;
    std::uint8_t count = 0U;
    std::array<AutomationTrustedKey, kAutomationTrustMaximumKeys> keys{};
};

enum class AutomationTrustLoadStatus : std::uint8_t {
    Loaded,
    Missing,
    Corrupt,
    Error,
};

enum class AutomationTrustMutationStatus : std::uint8_t {
    Applied,
    AuthenticationRequired,
    ConfirmationRequired,
    InvalidKey,
    DuplicateKey,
    KeyIdConflict,
    Full,
    NotFound,
    PersistenceFailed,
    StoreUnavailable,
};

const char* automationTrustLoadStatusName(AutomationTrustLoadStatus status);
const char* automationTrustMutationStatusName(
    AutomationTrustMutationStatus status);

class AutomationTrustStoreBackend {
public:
    virtual ~AutomationTrustStoreBackend() = default;
    virtual AutomationTrustLoadStatus load(
        AutomationTrustSnapshot* output) = 0;
    virtual bool save(const AutomationTrustSnapshot& snapshot) = 0;
};

struct AutomationTrustMutationAuthorization final {
    bool deviceUnlocked = false;
    bool confirmationFresh = false;
};

bool validAutomationTrustedKey(const AutomationTrustedKey& key);
bool validAutomationTrustSnapshot(const AutomationTrustSnapshot& snapshot);

using AutomationTrustRecord =
    std::array<std::uint8_t, kAutomationTrustRecordBytes>;

bool encodeAutomationTrustRecord(const AutomationTrustSnapshot& snapshot,
                                 AutomationTrustRecord* output);
bool decodeAutomationTrustRecord(const AutomationTrustRecord& record,
                                 AutomationTrustSnapshot* output);

class AutomationTrustStore final {
public:
    explicit AutomationTrustStore(AutomationTrustStoreBackend& backend)
        : backend_(backend) {}

    bool restore();
    AutomationTrustMutationStatus enroll(
        const AutomationTrustedKey& key,
        AutomationTrustMutationAuthorization authorization);
    AutomationTrustMutationStatus revoke(
        const std::array<std::uint8_t, kAutomationKeyIdBytes>& keyId,
        AutomationTrustMutationAuthorization authorization);

    const AutomationTrustSnapshot& snapshot() const { return snapshot_; }
    AutomationTrustLoadStatus loadStatus() const { return loadStatus_; }
    bool ready() const { return ready_; }

private:
    AutomationTrustStoreBackend& backend_;
    AutomationTrustSnapshot snapshot_{};
    AutomationTrustLoadStatus loadStatus_ = AutomationTrustLoadStatus::Error;
    bool ready_ = false;
};

const AutomationTrustedKey* findAutomationTrustedKey(
    const AutomationTrustSnapshot& snapshot,
    const std::array<std::uint8_t, kAutomationKeyIdBytes>& keyId);

}  // namespace leshy1::apps::automation
