#include "WifiChannelLoad.h"

#include <limits>

namespace leshy1::apps::wifi {

void WifiChannelLoad::reset() {
    snapshot_ = {};
    pendingBusyUs_.fill(0);
    pendingFrames_.fill(0);
    pendingPeakRssi_.fill(-127);
    cumulativeBusyPermille_.fill(0);
}

bool WifiChannelLoad::observe(std::uint8_t channel,
                              std::uint32_t estimatedAirtimeUs,
                              std::int16_t rssiDbm) {
    if (channel < kFirstChannel || channel > kLastChannel ||
        estimatedAirtimeUs == 0U) {
        return false;
    }
    const std::size_t at = index(channel);
    const std::uint32_t remaining =
        std::numeric_limits<std::uint32_t>::max() - pendingBusyUs_[at];
    pendingBusyUs_[at] += estimatedAirtimeUs > remaining
        ? remaining : estimatedAirtimeUs;
    if (pendingFrames_[at] != std::numeric_limits<std::uint16_t>::max()) {
        ++pendingFrames_[at];
    }
    if (rssiDbm > pendingPeakRssi_[at]) pendingPeakRssi_[at] = rssiDbm;
    if (snapshot_.framesObserved !=
        std::numeric_limits<std::uint32_t>::max()) {
        ++snapshot_.framesObserved;
    }
    return true;
}

bool WifiChannelLoad::completeDwell(std::uint8_t channel,
                                    std::uint32_t observedUs) {
    if (channel < kFirstChannel || channel > kLastChannel || observedUs == 0U) {
        return false;
    }
    const std::size_t at = index(channel);
    WifiChannelLoadBin& bin = snapshot_.channels[at];
    const std::uint64_t permille =
        static_cast<std::uint64_t>(pendingBusyUs_[at]) * 1000ULL / observedUs;
    const std::uint16_t currentBusyPermille = static_cast<std::uint16_t>(
        permille > 1000ULL ? 1000ULL : permille);
    bin.busyPermille = currentBusyPermille;
    if (bin.dwells != std::numeric_limits<std::uint32_t>::max()) {
        cumulativeBusyPermille_[at] += currentBusyPermille;
        ++bin.dwells;
    } else {
        // Preserve a bounded running mean even after an impractically long
        // session instead of allowing either counter to wrap.
        cumulativeBusyPermille_[at] -= bin.averageBusyPermille;
        cumulativeBusyPermille_[at] += currentBusyPermille;
    }
    bin.averageBusyPermille = static_cast<std::uint16_t>(
        cumulativeBusyPermille_[at] / bin.dwells);
    bin.frames = pendingFrames_[at];
    bin.peakRssiDbm = pendingFrames_[at] == 0U
        ? -127 : pendingPeakRssi_[at];
    bin.measured = true;
    snapshot_.measuredMask |= static_cast<std::uint16_t>(1U << at);
    ++snapshot_.completedDwells;
    if (channel == kLastChannel) ++snapshot_.completedSweeps;
    ++snapshot_.revision;
    pendingBusyUs_[at] = 0;
    pendingFrames_[at] = 0;
    pendingPeakRssi_[at] = -127;
    return true;
}

std::uint8_t WifiChannelLoad::bestPrimaryChannel() const {
    constexpr std::array<std::uint8_t, 3> primary = {1, 6, 11};
    constexpr std::uint16_t required =
        static_cast<std::uint16_t>((1U << 0U) | (1U << 5U) | (1U << 10U));
    if ((snapshot_.measuredMask & required) != required) return 0;
    std::uint8_t best = primary[0];
    for (std::size_t at = 1; at < primary.size(); ++at) {
        const std::uint8_t candidate = primary[at];
        if (snapshot_.channels[index(candidate)].averageBusyPermille <
            snapshot_.channels[index(best)].averageBusyPermille) {
            best = candidate;
        }
    }
    return best;
}

}  // namespace leshy1::apps::wifi
