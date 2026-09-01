#include "ProtocolComparison.h"

#include <algorithm>
#include <limits>

namespace leshy1::apps::protocol {
namespace {

bool identityMatchesAnalysis(const ProtocolAnnotationSource& identity,
                             const ProtocolWorkbenchAnalysis& analysis) {
    return identity.valid() && analysis.valid() &&
        identity.captureFingerprint == analysis.sourceFingerprint &&
        identity.pulseCount == analysis.pulseCount;
}

std::int32_t boundedDurationDelta(std::uint64_t left,
                                  std::uint64_t right) {
    const std::int64_t delta = static_cast<std::int64_t>(right) -
        static_cast<std::int64_t>(left);
    if (delta > std::numeric_limits<std::int32_t>::max()) {
        return std::numeric_limits<std::int32_t>::max();
    }
    if (delta < std::numeric_limits<std::int32_t>::min()) {
        return std::numeric_limits<std::int32_t>::min();
    }
    return static_cast<std::int32_t>(delta);
}

void appendChangedPulse(ProtocolComparisonResult& result,
                        std::uint16_t pulse, bool* omittedRegionOpen,
                        std::uint16_t* lastChangedPulse) {
    if (result.regionCount != 0U) {
        ProtocolComparisonRegion& previous =
            result.regions[result.regionCount - 1U];
        if (static_cast<std::uint32_t>(previous.lastPulse) + 1U == pulse) {
            previous.lastPulse = pulse;
            *omittedRegionOpen = false;
            *lastChangedPulse = pulse;
            return;
        }
    }
    if (result.regionCount < result.regions.size()) {
        result.regions[result.regionCount++] = {pulse, pulse};
        *omittedRegionOpen = false;
    } else if ((!*omittedRegionOpen ||
                static_cast<std::uint32_t>(*lastChangedPulse) + 1U != pulse) &&
               result.omittedRegions !=
                   std::numeric_limits<std::uint16_t>::max()) {
        ++result.omittedRegions;
        *omittedRegionOpen = true;
    }
    *lastChangedPulse = pulse;
}

}  // namespace

const char* protocolComparisonStatusName(ProtocolComparisonStatus status) {
    switch (status) {
        case ProtocolComparisonStatus::Valid: return "valid";
        case ProtocolComparisonStatus::InvalidArgument:
            return "invalid_argument";
        case ProtocolComparisonStatus::SourceMismatch:
            return "source_mismatch";
        case ProtocolComparisonStatus::SourceReadFailed:
            return "source_read_failed";
    }
    return "invalid_argument";
}

const char* protocolComparisonOutcomeName(ProtocolComparisonOutcome outcome) {
    switch (outcome) {
        case ProtocolComparisonOutcome::Identical: return "identical";
        case ProtocolComparisonOutcome::TimingVariation:
            return "timing_variation";
        case ProtocolComparisonOutcome::ValueChanged: return "value_changed";
        case ProtocolComparisonOutcome::StructureChanged:
            return "structure_changed";
    }
    return "structure_changed";
}

ProtocolComparisonStatus compareInfraredCaptures(
    const domain::captures::InfraredRawSource& leftSource,
    const ProtocolWorkbenchAnalysis& leftAnalysis,
    const ProtocolAnnotationSource& leftIdentity, bool leftStartLevel,
    const domain::captures::InfraredRawSource& rightSource,
    const ProtocolWorkbenchAnalysis& rightAnalysis,
    const ProtocolAnnotationSource& rightIdentity, bool rightStartLevel,
    ProtocolComparisonResult* output) {
    if (output == nullptr) return ProtocolComparisonStatus::InvalidArgument;
    *output = {};
    output->left = leftIdentity;
    output->right = rightIdentity;
    if (!leftAnalysis.valid() || !rightAnalysis.valid() ||
        leftSource.pulseCount() > ProtocolWorkbenchWorkspace::kMaximumPulses ||
        rightSource.pulseCount() > ProtocolWorkbenchWorkspace::kMaximumPulses) {
        output->status = ProtocolComparisonStatus::InvalidArgument;
        return output->status;
    }
    if (!identityMatchesAnalysis(leftIdentity, leftAnalysis) ||
        !identityMatchesAnalysis(rightIdentity, rightAnalysis) ||
        leftSource.pulseCount() != leftAnalysis.pulseCount ||
        rightSource.pulseCount() != rightAnalysis.pulseCount) {
        output->status = ProtocolComparisonStatus::SourceMismatch;
        return output->status;
    }

    const std::size_t common = std::min(leftSource.pulseCount(),
                                        rightSource.pulseCount());
    output->comparedPulses = static_cast<std::uint16_t>(common);
    output->durationDeltaUs = boundedDurationDelta(
        leftAnalysis.totalDurationUs, rightAnalysis.totalDurationUs);
    bool omittedRegionOpen = false;
    std::uint16_t lastChangedPulse = 0U;
    for (std::size_t index = 0U; index < common; ++index) {
        domain::captures::InfraredRawPulseView leftPulse;
        domain::captures::InfraredRawPulseView rightPulse;
        if (!leftSource.pulseView(index, &leftPulse) ||
            !rightSource.pulseView(index, &rightPulse)) {
            *output = {};
            output->left = leftIdentity;
            output->right = rightIdentity;
            output->status = ProtocolComparisonStatus::SourceReadFailed;
            return output->status;
        }
        if (leftPulse.durationUs != rightPulse.durationUs) {
            ++output->exactChangedPulses;
        }
        const std::uint16_t leftUnits = protocolNormalizedUnits(
            leftAnalysis, leftPulse.durationUs);
        const std::uint16_t rightUnits = protocolNormalizedUnits(
            rightAnalysis, rightPulse.durationUs);
        if (leftUnits != rightUnits) {
            ++output->valueChangedPulses;
            appendChangedPulse(*output, static_cast<std::uint16_t>(index),
                               &omittedRegionOpen, &lastChangedPulse);
        }
    }

    const bool structureChanged =
        leftSource.pulseCount() != rightSource.pulseCount() ||
        leftStartLevel != rightStartLevel;
    if (structureChanged) {
        output->outcome = ProtocolComparisonOutcome::StructureChanged;
    } else if (output->valueChangedPulses != 0U) {
        output->outcome = ProtocolComparisonOutcome::ValueChanged;
    } else if (output->exactChangedPulses != 0U ||
               leftIdentity.captureFingerprint !=
                   rightIdentity.captureFingerprint) {
        output->outcome = ProtocolComparisonOutcome::TimingVariation;
    } else {
        output->outcome = ProtocolComparisonOutcome::Identical;
    }
    output->status = ProtocolComparisonStatus::Valid;
    return output->status;
}

}  // namespace leshy1::apps::protocol
