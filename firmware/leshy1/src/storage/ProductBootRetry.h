#pragma once

#include <cstdint>

namespace leshy1::storage {

struct ProductBootRetryEvidence final {
    bool identityFailed = false;
    bool enrolled = false;
    bool expectedFingerprintValid = false;
    bool observedFingerprintEmpty = false;
    bool fingerprintMatched = false;
    bool mountedReadOnly = false;
    bool rootExists = false;
    bool opened = false;
    bool catalogAdmitted = false;
    bool missingMedia = false;
    bool cleanupComplete = false;
    std::uint32_t blockedWriteAttempts = 0;
    std::uint32_t ownedAfter = 0;
};

constexpr std::uint8_t kProductBootMaximumAttempts = 3;
constexpr std::uint32_t kProductBootRetryBaseDelayMs = 250;

// The caller must restart the MCU before the next attempt. Re-entering the raw
// identification + ESP-IDF mount stack in one boot is intentionally forbidden.
bool shouldRetryProductBootRecovery(const ProductBootRetryEvidence& evidence,
                                    std::uint8_t completedAttempts);

std::uint32_t productBootRetryDelayMs(std::uint8_t completedAttempts);

}  // namespace leshy1::storage
