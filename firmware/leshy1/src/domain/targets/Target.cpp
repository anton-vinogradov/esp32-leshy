#include "Target.h"

namespace leshy1::domain::targets {
namespace {

template <std::size_t Capacity>
bool anyNonZero(const std::array<std::uint8_t, Capacity>& bytes) {
    for (const std::uint8_t byte : bytes) {
        if (byte != 0) return true;
    }
    return false;
}

}  // namespace

bool targetIdValid(const TargetId& id) {
    return anyNonZero(id.bytes);
}

bool targetIdEqual(const TargetId& left, const TargetId& right) {
    return left.bytes == right.bytes;
}

bool sourceIdValid(const SourceId& id) {
    return anyNonZero(id.bytes);
}

bool targetIdentityValid(const TargetIdentity& identity) {
    if (identity.length != identity.value.size() ||
        !anyNonZero(identity.value)) {
        return false;
    }
    switch (identity.kind) {
        case TargetIdentityKind::WifiBssid:
        case TargetIdentityKind::WifiStation:
            return identity.discriminator == 0;
        case TargetIdentityKind::BleAddress:
            return identity.discriminator <= 3;
    }
    return false;
}

bool targetIdentityEqual(const TargetIdentity& left,
                         const TargetIdentity& right) {
    return left.kind == right.kind && left.value == right.value &&
        left.length == right.length &&
        left.discriminator == right.discriminator;
}

bool targetEvidenceValid(const TargetEvidenceRef& evidence) {
    return sourceIdValid(evidence.sourceId) &&
        evidence.sourceGeneration != 0 &&
        evidence.observationSequence != 0 &&
        evidence.observedMonotonicUs != 0;
}

bool targetEvidenceEqual(const TargetEvidenceRef& left,
                         const TargetEvidenceRef& right) {
    return left.sourceId.bytes == right.sourceId.bytes &&
        left.sourceGeneration == right.sourceGeneration &&
        left.observationSequence == right.observationSequence &&
        left.observedMonotonicUs == right.observedMonotonicUs;
}

}  // namespace leshy1::domain::targets
