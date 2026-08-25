#include "ObservationTargetAdapter.h"

namespace leshy1::services::targets {

const char* observationTargetStatusName(ObservationTargetStatus status) {
    switch (status) {
        case ObservationTargetStatus::Valid: return "valid";
        case ObservationTargetStatus::InvalidArgument: return "invalid_argument";
        case ObservationTargetStatus::IdentityUnavailable:
            return "identity_unavailable";
        case ObservationTargetStatus::BleAddressTypeUnavailable:
            return "ble_address_type_unavailable";
    }
    return "invalid_argument";
}

ObservationTargetAdmission admitObservationToTarget(
    const domain::targets::SourceId& sourceId,
    std::uint32_t sourceGeneration,
    const domain::observations::Observation& observation) {
    ObservationTargetAdmission result{};
    if (!domain::targets::sourceIdValid(sourceId) || sourceGeneration == 0 ||
        observation.sequence == 0 || observation.monotonicUs == 0) {
        return result;
    }
    if (observation.identityLength !=
        domain::targets::TargetIdentity::kValueCapacity) {
        result.status = ObservationTargetStatus::IdentityUnavailable;
        return result;
    }

    result.identity.value = observation.identity;
    result.identity.length = observation.identityLength;
    switch (observation.radio) {
        case domain::observations::RadioKind::Wifi:
            result.identity.kind =
                domain::targets::TargetIdentityKind::WifiBssid;
            result.identity.discriminator = 0;
            break;
        case domain::observations::RadioKind::Ble:
            if (!observation.bleAdvertisement.present ||
                observation.bleAdvertisement.addressType > 3) {
                result.status =
                    ObservationTargetStatus::BleAddressTypeUnavailable;
                return result;
            }
            result.identity.kind =
                domain::targets::TargetIdentityKind::BleAddress;
            result.identity.discriminator =
                observation.bleAdvertisement.addressType;
            break;
        default:
            return result;
    }
    if (!domain::targets::targetIdentityValid(result.identity)) {
        result.status = ObservationTargetStatus::IdentityUnavailable;
        return result;
    }
    result.evidence.sourceId = sourceId;
    result.evidence.sourceGeneration = sourceGeneration;
    result.evidence.observationSequence = observation.sequence;
    result.evidence.observedMonotonicUs = observation.monotonicUs;
    if (!domain::targets::targetEvidenceValid(result.evidence)) return result;
    result.status = ObservationTargetStatus::Valid;
    return result;
}

}  // namespace leshy1::services::targets
