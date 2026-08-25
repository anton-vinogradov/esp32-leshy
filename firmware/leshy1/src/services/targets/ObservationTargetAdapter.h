#pragma once

#include <cstdint>

#include "domain/observations/Observation.h"
#include "domain/targets/Target.h"

namespace leshy1::services::targets {

enum class ObservationTargetStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    IdentityUnavailable,
    BleAddressTypeUnavailable,
};

const char* observationTargetStatusName(ObservationTargetStatus status);

struct ObservationTargetAdmission final {
    ObservationTargetStatus status = ObservationTargetStatus::InvalidArgument;
    domain::targets::TargetIdentity identity{};
    domain::targets::TargetEvidenceRef evidence{};

    bool valid() const { return status == ObservationTargetStatus::Valid; }
};

ObservationTargetAdmission admitObservationToTarget(
    const domain::targets::SourceId& sourceId, std::uint32_t sourceGeneration,
    const domain::observations::Observation& observation);

}  // namespace leshy1::services::targets
