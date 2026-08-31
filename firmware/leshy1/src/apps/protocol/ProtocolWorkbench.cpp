#include "ProtocolWorkbench.h"

#include <algorithm>
#include <limits>

namespace leshy1::apps::protocol {

namespace {

constexpr std::uint64_t kFnv1aOffset = 14695981039346656037ULL;
constexpr std::uint64_t kFnv1aPrime = 1099511628211ULL;

std::uint64_t appendFingerprintByte(std::uint64_t hash, std::uint8_t value) {
    return (hash ^ value) * kFnv1aPrime;
}

std::uint64_t appendFingerprintDuration(std::uint64_t hash,
                                        std::uint16_t durationUs) {
    hash = appendFingerprintByte(
        hash, static_cast<std::uint8_t>(durationUs & 0xFFU));
    return appendFingerprintByte(
        hash, static_cast<std::uint8_t>((durationUs >> 8U) & 0xFFU));
}

bool startsNewBand(std::uint16_t durationUs, std::uint32_t centerUs) {
    // Demodulated receivers jitter. A 50% ratio plus a small absolute guard
    // keeps a real 560 us family together while separating 560/1690 NEC
    // symbols. This is deliberately protocol-neutral and explanatory, not a
    // decoder claiming a match.
    const std::uint32_t threshold = centerUs + centerUs / 2U + 80U;
    return static_cast<std::uint32_t>(durationUs) > threshold;
}

}  // namespace

const char* protocolWorkbenchStatusName(ProtocolWorkbenchStatus status) {
    switch (status) {
        case ProtocolWorkbenchStatus::Valid: return "valid";
        case ProtocolWorkbenchStatus::InvalidArgument:
            return "invalid_argument";
        case ProtocolWorkbenchStatus::TooFewPulses: return "too_few_pulses";
        case ProtocolWorkbenchStatus::SourceReadFailed:
            return "source_read_failed";
    }
    return "invalid_argument";
}

ProtocolWorkbenchStatus analyzeInfraredCapture(
    const domain::captures::InfraredRawSource& source,
    ProtocolWorkbenchWorkspace& workspace,
    ProtocolWorkbenchAnalysis* output) {
    if (output == nullptr) return ProtocolWorkbenchStatus::InvalidArgument;
    *output = {};
    const std::size_t count = source.pulseCount();
    output->pulseCount = count;
    if (count < 2U) {
        output->status = ProtocolWorkbenchStatus::TooFewPulses;
        return output->status;
    }
    if (count > workspace.sortedDurations.size()) {
        output->status = ProtocolWorkbenchStatus::InvalidArgument;
        return output->status;
    }

    std::uint16_t shortest = std::numeric_limits<std::uint16_t>::max();
    std::uint16_t longest = 0U;
    std::uint64_t total = 0U;
    std::uint64_t fingerprint = kFnv1aOffset;
    fingerprint = appendFingerprintByte(
        fingerprint, static_cast<std::uint8_t>(count & 0xFFU));
    fingerprint = appendFingerprintByte(
        fingerprint, static_cast<std::uint8_t>((count >> 8U) & 0xFFU));
    for (std::size_t index = 0U; index < count; ++index) {
        domain::captures::InfraredRawPulseView pulse;
        if (!source.pulseView(index, &pulse) || pulse.durationUs == 0U) {
            output->status = ProtocolWorkbenchStatus::SourceReadFailed;
            return output->status;
        }
        workspace.sortedDurations[index] = pulse.durationUs;
        shortest = std::min(shortest, pulse.durationUs);
        longest = std::max(longest, pulse.durationUs);
        total += pulse.durationUs;
        fingerprint = appendFingerprintDuration(fingerprint,
                                                pulse.durationUs);
    }
    std::sort(workspace.sortedDurations.begin(),
              workspace.sortedDurations.begin() +
                  static_cast<std::ptrdiff_t>(count));

    std::size_t bandIndex = 0U;
    std::uint32_t bandSum = 0U;
    for (std::size_t index = 0U; index < count; ++index) {
        const std::uint16_t duration = workspace.sortedDurations[index];
        ProtocolTimingBand* band = &output->bands[bandIndex];
        const std::uint32_t center = band->samples == 0U
            ? duration : bandSum / band->samples;
        if (band->samples != 0U && startsNewBand(duration, center) &&
            bandIndex + 1U < output->bands.size()) {
            band->centerUs = static_cast<std::uint16_t>(center);
            ++bandIndex;
            band = &output->bands[bandIndex];
            bandSum = 0U;
        }
        if (band->samples == 0U) band->minimumUs = duration;
        band->maximumUs = duration;
        bandSum += duration;
        ++band->samples;
        band->centerUs = static_cast<std::uint16_t>(bandSum / band->samples);
    }

    output->status = ProtocolWorkbenchStatus::Valid;
    output->totalDurationUs = total;
    output->shortestPulseUs = shortest;
    output->longestPulseUs = longest;
    output->bandCount = bandIndex + 1U;
    output->baseUnitUs = output->bands[0].centerUs;
    output->sourceFingerprint = fingerprint;
    return output->status;
}

std::uint8_t protocolTimingBandFor(
    const ProtocolWorkbenchAnalysis& analysis, std::uint16_t durationUs) {
    if (!analysis.valid() || analysis.bandCount == 0U || durationUs == 0U) {
        return 0xFFU;
    }
    std::size_t closest = 0U;
    std::uint32_t closestDistance = std::numeric_limits<std::uint32_t>::max();
    for (std::size_t index = 0U; index < analysis.bandCount; ++index) {
        const std::uint16_t center = analysis.bands[index].centerUs;
        const std::uint32_t distance = durationUs > center
            ? static_cast<std::uint32_t>(durationUs - center)
            : static_cast<std::uint32_t>(center - durationUs);
        if (distance < closestDistance) {
            closest = index;
            closestDistance = distance;
        }
    }
    return static_cast<std::uint8_t>(closest);
}

std::uint16_t protocolNormalizedUnits(
    const ProtocolWorkbenchAnalysis& analysis, std::uint16_t durationUs) {
    if (!analysis.valid() || analysis.baseUnitUs == 0U || durationUs == 0U) {
        return 0U;
    }
    const std::uint32_t rounded =
        static_cast<std::uint32_t>(durationUs) + analysis.baseUnitUs / 2U;
    const std::uint32_t units = rounded / analysis.baseUnitUs;
    return static_cast<std::uint16_t>(units == 0U ? 1U : units);
}

}  // namespace leshy1::apps::protocol
