#pragma once

#include <cstdint>

#include "storage/SdIdentificationTransport.h"

namespace leshy1::storage {

struct ProductStartIdentityRetryEvidence final {
    bool explicitStart = false;
    bool enrolled = false;
    bool expectedFingerprintValid = false;
    bool requiredResourcesHeld = false;
    bool physicalSpiStarted = false;
    SdTransportRunStatus identityStatus = SdTransportRunStatus::InvalidPlan;
    bool observedFingerprintEmpty = false;
    bool identityCleanupComplete = false;
    bool filesystemAttempted = false;
};

constexpr std::uint8_t kProductStartMaximumIdentityAttempts = 8;
constexpr std::uint32_t kProductStartIdentityRetryBaseDelayMs = 250;

// Only raw, read-only identification may be repeated here. The caller must not
// have attempted a filesystem mount or write before consulting this policy.
bool shouldRetryProductStartIdentity(
    const ProductStartIdentityRetryEvidence& evidence,
    std::uint8_t completedAttempts);

std::uint32_t productStartIdentityRetryDelayMs(
    std::uint8_t completedAttempts);

}  // namespace leshy1::storage
