#include "storage/ProductStartRetry.h"

namespace leshy1::storage {

bool shouldRetryProductStartIdentity(
    const ProductStartIdentityRetryEvidence& evidence,
    std::uint8_t completedAttempts) {
    const bool transientWireFailure =
        evidence.identityStatus == SdTransportRunStatus::ExchangeFailed ||
        evidence.identityStatus == SdTransportRunStatus::InitTimeout ||
        evidence.identityStatus == SdTransportRunStatus::ParseRejected;
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

bool shouldRetryProductStartFilesystem(
    const ProductStartFilesystemRetryEvidence& evidence,
    std::uint8_t completedAttempts) {
    return completedAttempts > 0 &&
           completedAttempts < kProductStartMaximumFilesystemAttempts &&
           evidence.explicitStart && evidence.enrolled &&
           evidence.expectedFingerprintValid &&
           evidence.requiredResourcesHeld && evidence.identityValid &&
           evidence.identityCleanupComplete &&
           evidence.observedFingerprintMatches && evidence.mountAttempted &&
           !evidence.mountSucceeded &&
           evidence.mountError == kProductStartTransientFilesystemMountError &&
           evidence.filesystemCleanupComplete &&
           !evidence.filesystemStillMounted &&
           !evidence.storeCurrentlyOpen && !evidence.radioCurrentlyActive &&
           !evidence.cancelRequested;
}

std::uint32_t productStartFilesystemRetryDelayMs(
    std::uint8_t completedAttempts) {
    if (completedAttempts == 0 ||
        completedAttempts >= kProductStartMaximumFilesystemAttempts) {
        return 0;
    }
    return kProductStartFilesystemRetryBaseDelayMs * completedAttempts;
}

}  // namespace leshy1::storage
