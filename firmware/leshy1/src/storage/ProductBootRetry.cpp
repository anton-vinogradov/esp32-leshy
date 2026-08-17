#include "storage/ProductBootRetry.h"

namespace leshy1::storage {

bool isProductBootRetryReset(bool softwareReset,
                             bool watchdogReset,
                             bool timeoutRecorded) {
    return softwareReset || (watchdogReset && timeoutRecorded);
}

bool shouldResetProductBootRetryState(bool retryReset,
                                      bool rtcMagicValid,
                                      bool currentAppIdentityValid,
                                      bool appIdentityMatches) {
    return !retryReset || !rtcMagicValid || !currentAppIdentityValid ||
           !appIdentityMatches;
}

bool shouldRetryProductBootRecovery(const ProductBootRetryEvidence& evidence,
                                    std::uint8_t completedAttempts) {
    return completedAttempts > 0 &&
           completedAttempts < kProductBootMaximumAttempts &&
           evidence.identityFailed && evidence.enrolled &&
           evidence.expectedFingerprintValid &&
           evidence.observedFingerprintEmpty &&
           !evidence.fingerprintMatched && !evidence.mountedReadOnly &&
           !evidence.rootExists && !evidence.opened &&
           !evidence.catalogAdmitted && evidence.missingMedia &&
           evidence.cleanupComplete && evidence.blockedWriteAttempts == 0 &&
           evidence.ownedAfter == 0;
}

std::uint32_t productBootRetryDelayMs(std::uint8_t completedAttempts) {
    if (completedAttempts == 0 ||
        completedAttempts >= kProductBootMaximumAttempts) {
        return 0;
    }
    return kProductBootRetryBaseDelayMs * completedAttempts;
}

}  // namespace leshy1::storage
