#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/captures/InfraredRaw.h"

namespace leshy1::apps::protocol {

enum class ProtocolWorkbenchStatus : std::uint8_t {
    Valid,
    InvalidArgument,
    TooFewPulses,
    SourceReadFailed,
};

const char* protocolWorkbenchStatusName(ProtocolWorkbenchStatus status);

struct ProtocolTimingBand final {
    std::uint16_t centerUs = 0U;
    std::uint16_t minimumUs = 0U;
    std::uint16_t maximumUs = 0U;
    std::uint16_t samples = 0U;
};

struct ProtocolWorkbenchAnalysis final {
    static constexpr std::size_t kMaximumBands = 4U;

    ProtocolWorkbenchStatus status = ProtocolWorkbenchStatus::InvalidArgument;
    std::size_t pulseCount = 0U;
    std::uint64_t totalDurationUs = 0U;
    std::uint16_t shortestPulseUs = 0U;
    std::uint16_t longestPulseUs = 0U;
    std::uint16_t baseUnitUs = 0U;
    std::array<ProtocolTimingBand, kMaximumBands> bands{};
    std::size_t bandCount = 0U;
    std::uint64_t sourceFingerprint = 0U;

    bool valid() const { return status == ProtocolWorkbenchStatus::Valid; }
};

// The workspace is explicit so analysis never allocates and never borrows a
// mutable view of the source Capture. One workspace is enough for the maximum
// persisted IR envelope supported by SessionCodec.
struct ProtocolWorkbenchWorkspace final {
    static constexpr std::size_t kMaximumPulses = 512U;
    std::array<std::uint16_t, kMaximumPulses> sortedDurations{};
};

ProtocolWorkbenchStatus analyzeInfraredCapture(
    const domain::captures::InfraredRawSource& source,
    ProtocolWorkbenchWorkspace& workspace,
    ProtocolWorkbenchAnalysis* output);

std::uint8_t protocolTimingBandFor(
    const ProtocolWorkbenchAnalysis& analysis, std::uint16_t durationUs);

std::uint16_t protocolNormalizedUnits(
    const ProtocolWorkbenchAnalysis& analysis, std::uint16_t durationUs);

}  // namespace leshy1::apps::protocol
