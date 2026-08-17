#include "storage/ProductStartRetry.h"

namespace leshy1::storage {

bool shouldRetryProductStartIdentity(
    const ProductStartIdentityRetryEvidence& evidence,
    std::uint8_t completedAttempts) {
    const bool transientWireFailure =
        evidence.identityStatus == SdTransportRunStatus::ExchangeFailed ||
        evidence.identityStatus == SdTransportRunStatus::InitTimeout;
    return completedAttempts > 0 &&
           completedAttempts < kProductStartMaximumIdentityAttempts &&
           evidence.explicitStart && evidence.enrolled &&
           evidence.expectedFingerprintValid &&
           evidence.requiredResourcesHeld && evidence.physicalSpiStarted &&
           transientWireFailure && evidence.observedFingerprintEmpty &&
           evidence.identityCleanupComplete && !evidence.filesystemAttempted;
}

std::uint32_t productStartIdentityRetryDelayMs(
    std::uint8_t completedAttempts) {
    if (completedAttempts == 0 ||
        completedAttempts >= kProductStartMaximumIdentityAttempts) {
        return 0;
    }
    return kProductStartIdentityRetryBaseDelayMs * completedAttempts;
}

}  // namespace leshy1::storage
