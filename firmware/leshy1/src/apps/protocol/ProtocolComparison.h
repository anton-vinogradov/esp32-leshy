#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "ProtocolAnnotations.h"
#include "ProtocolWorkbench.h"

namespace leshy1::apps::protocol {

enum class ProtocolComparisonStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    SourceMismatch,
    SourceReadFailed,
};

enum class ProtocolComparisonOutcome : std::uint8_t {
    Identical,
    TimingVariation,
    ValueChanged,
    StructureChanged,
};

const char* protocolComparisonStatusName(ProtocolComparisonStatus status);
const char* protocolComparisonOutcomeName(ProtocolComparisonOutcome outcome);

struct ProtocolComparisonRegion final {
    std::uint16_t firstPulse = 0U;
    std::uint16_t lastPulse = 0U;
};

// A bounded derived result. It references two exact immutable Captures and
// stores only the useful difference summary, never their raw pulse arrays.
struct ProtocolComparisonResult final {
    static constexpr std::size_t kMaximumRegions = 16U;

    ProtocolComparisonStatus status = ProtocolComparisonStatus::InvalidArgument;
    ProtocolComparisonOutcome outcome = ProtocolComparisonOutcome::StructureChanged;
    ProtocolAnnotationSource left{};
    ProtocolAnnotationSource right{};
    std::array<ProtocolComparisonRegion, kMaximumRegions> regions{};
    std::size_t regionCount = 0U;
    std::uint16_t comparedPulses = 0U;
    std::uint16_t valueChangedPulses = 0U;
    std::uint16_t exactChangedPulses = 0U;
    std::uint16_t omittedRegions = 0U;
    std::int32_t durationDeltaUs = 0;

    bool valid() const { return status == ProtocolComparisonStatus::Valid; }
};

ProtocolComparisonStatus compareInfraredCaptures(
    const domain::captures::InfraredRawSource& leftSource,
    const ProtocolWorkbenchAnalysis& leftAnalysis,
    const ProtocolAnnotationSource& leftIdentity, bool leftStartLevel,
    const domain::captures::InfraredRawSource& rightSource,
    const ProtocolWorkbenchAnalysis& rightAnalysis,
    const ProtocolAnnotationSource& rightIdentity, bool rightStartLevel,
    ProtocolComparisonResult* output);

}  // namespace leshy1::apps::protocol
