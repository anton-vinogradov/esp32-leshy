#include "TargetComparison.h"

#include <cstring>
#include <memory>
#include <new>
#include <type_traits>

namespace leshy1::domain::targets {
namespace {

struct EvidenceSnapshot final {
    TargetComparisonEvidence evidence{};
    observations::Observation observation{};
};

struct SideSnapshot final {
    std::array<EvidenceSnapshot, TargetRecord::kIdentityCapacity> values{};
    std::uint8_t count = 0;
};

struct ComparisonScratch final {
    SideSnapshot baseline{};
    SideSnapshot current{};
};

static_assert(sizeof(ComparisonScratch) == 1616U,
              "comparison scratch budget changed");

bool evidenceBelongsTo(const TargetEvidenceRef& evidence,
                       const TargetComparisonSource& source) {
    return evidence.sourceId.bytes == source.id.bytes &&
        evidence.sourceGeneration == source.generation;
}

bool observationIdentity(const observations::Observation& observation,
                         TargetIdentity* output) {
    if (output == nullptr ||
        observation.sequence == 0 || observation.monotonicUs == 0 ||
        observation.identityLength != TargetIdentity::kValueCapacity ||
        observation.labelLength > observations::Observation::kLabelCapacity ||
        observation.label[observation.labelLength] != '\0' ||
        observation.rssiDbm < -127 || observation.rssiDbm > 0) {
        return false;
    }
    TargetIdentity identity{};
    identity.value = observation.identity;
    identity.length = observation.identityLength;
    switch (observation.radio) {
        case observations::RadioKind::Wifi:
            if (observation.channel == 0 || observation.channel > 14 ||
                observation.frequencyKhz == 0) {
                return false;
            }
            identity.kind = TargetIdentityKind::WifiBssid;
            identity.discriminator = 0;
            break;
        case observations::RadioKind::Ble:
            if (!observation.bleAdvertisement.present ||
                observation.bleAdvertisement.addressType > 3U ||
                observation.channel != 0 || observation.frequencyKhz != 0) {
                return false;
            }
            identity.kind = TargetIdentityKind::BleAddress;
            identity.discriminator =
                observation.bleAdvertisement.addressType;
            break;
        default:
            return false;
    }
    if (!targetIdentityValid(identity)) return false;
    *output = identity;
    return true;
}

std::size_t identityIndex(const TargetRecord& target,
                          const TargetIdentity& identity) {
    for (std::size_t index = 0; index < target.identityCount; ++index) {
        if (targetIdentityEqual(target.identities[index], identity)) {
            return index;
        }
    }
    return target.identities.size();
}

bool newerEvidence(const TargetEvidenceRef& candidate,
                   const TargetEvidenceRef& current) {
    return candidate.observedMonotonicUs > current.observedMonotonicUs ||
        (candidate.observedMonotonicUs == current.observedMonotonicUs &&
         candidate.observationSequence > current.observationSequence);
}

TargetComparisonStatus buildSide(
    const TargetRecord& target, const TargetComparisonSource& source,
    const TargetComparisonEvidenceLookup& lookup, SideSnapshot* output) {
    if (output == nullptr) return TargetComparisonStatus::InvalidArgument;
    *output = {};
    for (std::size_t index = 0; index < target.evidenceCount; ++index) {
        const TargetEvidenceRef& reference = target.evidence[index];
        if (!evidenceBelongsTo(reference, source)) continue;
        observations::Observation observation{};
        if (!lookup.loadExact(reference, &observation)) {
            return TargetComparisonStatus::EvidenceUnavailable;
        }
        if (observation.sequence != reference.observationSequence ||
            observation.monotonicUs != reference.observedMonotonicUs) {
            return TargetComparisonStatus::EvidenceMismatch;
        }
        TargetIdentity identity{};
        if (!observationIdentity(observation, &identity)) {
            return TargetComparisonStatus::EvidenceMismatch;
        }
        const std::size_t targetIdentityIndex = identityIndex(target, identity);
        if (targetIdentityIndex >= target.identityCount) {
            return TargetComparisonStatus::EvidenceMismatch;
        }
        EvidenceSnapshot* latest = nullptr;
        for (std::size_t sideIndex = 0; sideIndex < output->count;
             ++sideIndex) {
            if (targetIdentityEqual(output->values[sideIndex].evidence.identity,
                                    identity)) {
                latest = &output->values[sideIndex];
                break;
            }
        }
        if (latest == nullptr) {
            if (output->count >= output->values.size()) {
                return TargetComparisonStatus::ResultFull;
            }
            latest = &output->values[output->count++];
        }
        if (!targetEvidenceValid(latest->evidence.reference) ||
            newerEvidence(reference, latest->evidence.reference)) {
            latest->evidence = {identity, reference};
            latest->observation = observation;
        }
    }
    return TargetComparisonStatus::Compared;
}

const EvidenceSnapshot* findIdentity(const SideSnapshot& side,
                                     const TargetIdentity& identity) {
    for (std::size_t index = 0; index < side.count; ++index) {
        if (targetIdentityEqual(side.values[index].evidence.identity,
                                identity)) {
            return &side.values[index];
        }
    }
    return nullptr;
}

TargetChangeMask compareObservation(
    const observations::Observation& baseline,
    const observations::Observation& current) {
    TargetChangeMask changes = 0;
    if (baseline.radio != current.radio) {
        changes |= targetChangeMask(TargetChangeKind::Radio);
    }
    if (baseline.frequencyKhz != current.frequencyKhz) {
        changes |= targetChangeMask(TargetChangeKind::Frequency);
    }
    if (baseline.channel != current.channel) {
        changes |= targetChangeMask(TargetChangeKind::Channel);
    }
    const std::int32_t signalDelta =
        static_cast<std::int32_t>(current.rssiDbm) - baseline.rssiDbm;
    if (signalDelta >= kMeaningfulTargetSignalDeltaDb ||
        signalDelta <= -kMeaningfulTargetSignalDeltaDb) {
        changes |= targetChangeMask(TargetChangeKind::Signal);
    }
    if (baseline.labelLength != current.labelLength ||
        std::memcmp(baseline.label.data(), current.label.data(),
                    baseline.labelLength) != 0) {
        changes |= targetChangeMask(TargetChangeKind::Label);
    }
    if (!observations::wifiNetworkFactsEqual(
            baseline.wifiNetwork, current.wifiNetwork)) {
        changes |= targetChangeMask(TargetChangeKind::WifiFacts);
    }
    if (!observations::bleAdvertisementFactsEqual(
            baseline.bleAdvertisement, current.bleAdvertisement)) {
        changes |= targetChangeMask(TargetChangeKind::BleFacts);
    }
    return changes;
}

TargetChangeMask compareSides(const SideSnapshot& baseline,
                              const SideSnapshot& current) {
    TargetChangeMask changes = 0;
    if (baseline.count != current.count) {
        changes |= targetChangeMask(TargetChangeKind::IdentitySet);
    }
    for (std::size_t index = 0; index < baseline.count; ++index) {
        const EvidenceSnapshot& baselineValue = baseline.values[index];
        const EvidenceSnapshot* currentValue = findIdentity(
            current, baselineValue.evidence.identity);
        if (currentValue == nullptr) {
            changes |= targetChangeMask(TargetChangeKind::IdentitySet);
            continue;
        }
        changes |= compareObservation(baselineValue.observation,
                                      currentValue->observation);
    }
    for (std::size_t index = 0; index < current.count; ++index) {
        if (findIdentity(baseline, current.values[index].evidence.identity) ==
            nullptr) {
            changes |= targetChangeMask(TargetChangeKind::IdentitySet);
        }
    }
    return changes;
}

void copyEvidence(const SideSnapshot& source,
                  std::array<TargetComparisonEvidence,
                             TargetComparisonItem::kEvidencePerSideCapacity>*
                      destination,
                  std::uint8_t* count) {
    *destination = {};
    *count = source.count;
    for (std::size_t index = 0; index < source.count; ++index) {
        (*destination)[index] = source.values[index].evidence;
    }
}

void incrementClassCount(TargetComparisonResult* result,
                         TargetComparisonClass classification) {
    switch (classification) {
        case TargetComparisonClass::Added: ++result->added; break;
        case TargetComparisonClass::Removed: ++result->removed; break;
        case TargetComparisonClass::Changed: ++result->changed; break;
        case TargetComparisonClass::Unchanged: ++result->unchanged; break;
    }
}

}  // namespace

bool targetComparisonSourceValid(const TargetComparisonSource& source) {
    return sourceIdValid(source.id) && source.generation != 0;
}

bool targetComparisonSourceEqual(const TargetComparisonSource& left,
                                 const TargetComparisonSource& right) {
    return left.id.bytes == right.id.bytes &&
        left.generation == right.generation;
}

const char* targetComparisonStatusName(TargetComparisonStatus status) {
    switch (status) {
        case TargetComparisonStatus::Compared: return "compared";
        case TargetComparisonStatus::InvalidArgument: return "invalid_argument";
        case TargetComparisonStatus::SourceUnavailable:
            return "source_unavailable";
        case TargetComparisonStatus::EvidenceUnavailable:
            return "evidence_unavailable";
        case TargetComparisonStatus::EvidenceMismatch:
            return "evidence_mismatch";
        case TargetComparisonStatus::ResultFull: return "result_full";
        case TargetComparisonStatus::ScratchUnavailable:
            return "scratch_unavailable";
    }
    return "invalid_argument";
}

const char* targetComparisonClassName(
    TargetComparisonClass classification) {
    switch (classification) {
        case TargetComparisonClass::Added: return "added";
        case TargetComparisonClass::Removed: return "removed";
        case TargetComparisonClass::Changed: return "changed";
        case TargetComparisonClass::Unchanged: return "unchanged";
    }
    return "unchanged";
}

void resetTargetComparisonResult(TargetComparisonResult* output,
                                 TargetComparisonStatus status) {
    if (output == nullptr) return;
    static_assert(std::is_trivially_copyable_v<TargetComparisonResult>,
                  "in-place reset requires byte-clearable result storage");
    std::memset(static_cast<void*>(output), 0, sizeof(*output));
    output->status = status;
    for (auto& item : output->items) {
        item.classification = TargetComparisonClass::Unchanged;
    }
}

TargetComparisonStatus compareTargetSessionsInto(
    const TargetCatalog& catalog, const TargetComparisonSource& baseline,
    const TargetComparisonSource& current,
    const TargetComparisonEvidenceLookup& evidenceLookup,
    TargetComparisonResult* output) {
    if (output == nullptr) return TargetComparisonStatus::InvalidArgument;
    resetTargetComparisonResult(output, TargetComparisonStatus::InvalidArgument);
    if (!targetComparisonSourceValid(baseline) ||
        !targetComparisonSourceValid(current) ||
        targetComparisonSourceEqual(baseline, current)) {
        return output->status;
    }
    if (!evidenceLookup.sourceAvailable(baseline) ||
        !evidenceLookup.sourceAvailable(current)) {
        output->status = TargetComparisonStatus::SourceUnavailable;
        return output->status;
    }
    std::unique_ptr<ComparisonScratch> scratch(
        new (std::nothrow) ComparisonScratch());
    if (!scratch) {
        output->status = TargetComparisonStatus::ScratchUnavailable;
        return output->status;
    }
    output->baseline = baseline;
    output->current = current;

    for (std::size_t targetIndex = 0; targetIndex < catalog.size();
         ++targetIndex) {
        const TargetRecord* target = catalog.get(targetIndex);
        if (target == nullptr || target->identityCount == 0 ||
            target->identityCount > target->identities.size() ||
            target->evidenceCount == 0 ||
            target->evidenceCount > target->evidence.size()) {
            resetTargetComparisonResult(
                output, TargetComparisonStatus::InvalidArgument);
            return output->status;
        }
        SideSnapshot& baselineSide = scratch->baseline;
        SideSnapshot& currentSide = scratch->current;
        const TargetComparisonStatus baselineStatus = buildSide(
            *target, baseline, evidenceLookup, &baselineSide);
        if (baselineStatus != TargetComparisonStatus::Compared) {
            resetTargetComparisonResult(output, baselineStatus);
            return output->status;
        }
        const TargetComparisonStatus currentStatus = buildSide(
            *target, current, evidenceLookup, &currentSide);
        if (currentStatus != TargetComparisonStatus::Compared) {
            resetTargetComparisonResult(output, currentStatus);
            return output->status;
        }
        if (baselineSide.count == 0 && currentSide.count == 0) continue;
        if (output->size >= output->items.size()) {
            resetTargetComparisonResult(output,
                                        TargetComparisonStatus::ResultFull);
            return output->status;
        }

        TargetComparisonItem& item = output->items[output->size++];
        item.targetId = target->id;
        copyEvidence(baselineSide, &item.baselineEvidence,
                     &item.baselineEvidenceCount);
        copyEvidence(currentSide, &item.currentEvidence,
                     &item.currentEvidenceCount);
        if (baselineSide.count == 0) {
            item.classification = TargetComparisonClass::Added;
        } else if (currentSide.count == 0) {
            item.classification = TargetComparisonClass::Removed;
        } else {
            item.changes = compareSides(baselineSide, currentSide);
            item.classification = item.changes == 0
                ? TargetComparisonClass::Unchanged
                : TargetComparisonClass::Changed;
        }
        incrementClassCount(output, item.classification);
    }
    output->status = TargetComparisonStatus::Compared;
    return output->status;
}

static_assert(sizeof(TargetComparisonResult) <= 12U * 1024U,
              "bounded comparison result must remain below 12 KiB");

}  // namespace leshy1::domain::targets
