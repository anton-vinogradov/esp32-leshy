#pragma once

#include <cstdint>

#include "domain/observations/Observation.h"
#include "services/survey/SourceTimeline.h"

namespace leshy1::services::survey {

enum class SourceFailureClass : std::uint8_t {
    Unavailable,
    Fault,
};

struct SourceDegradationDecision final {
    bool valid = false;
    bool continueSession = false;
    std::uint8_t activeSourceMask = 0;
    std::uint8_t unavailableSourceMask = 0;
    SourceWindowState windowState = SourceWindowState::Fault;
    SourceWindowReason windowReason = SourceWindowReason::DriverFault;
    const char* status = "invalid_source_failure";
};

// Removes exactly one failed source from the active schedule while preserving
// the user's selected-source mask in the timeline. The remaining source may
// continue; loss of the final source is a terminal failure.
SourceDegradationDecision decideSourceDegradation(
    std::uint8_t activeSourceMask, std::uint8_t unavailableSourceMask,
    domain::observations::RadioKind failedSource,
    SourceFailureClass failureClass);

}  // namespace leshy1::services::survey
