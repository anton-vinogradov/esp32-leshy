#include "SourceDegradation.h"

namespace leshy1::services::survey {

SourceDegradationDecision decideSourceDegradation(
    std::uint8_t activeSourceMask, std::uint8_t unavailableSourceMask,
    domain::observations::RadioKind failedSource,
    SourceFailureClass failureClass) {
    SourceDegradationDecision decision;
    const std::uint8_t failedMask = sourceMask(failedSource);
    if (failedMask == 0 || (activeSourceMask & failedMask) == 0) {
        return decision;
    }
    decision.valid = true;
    decision.activeSourceMask = static_cast<std::uint8_t>(
        activeSourceMask & static_cast<std::uint8_t>(~failedMask));
    decision.unavailableSourceMask = static_cast<std::uint8_t>(
        unavailableSourceMask | failedMask);
    decision.continueSession = decision.activeSourceMask != 0;
    decision.status = decision.continueSession
        ? "source_degraded" : "all_sources_failed";
    if (failureClass == SourceFailureClass::Unavailable) {
        decision.windowState = SourceWindowState::Unavailable;
        decision.windowReason = SourceWindowReason::DriverUnavailable;
    }
    return decision;
}

}  // namespace leshy1::services::survey
