#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::apps::wifi {

struct WifiChannelLoadBin final {
    std::uint16_t busyPermille = 0;
    std::uint16_t averageBusyPermille = 0;
    std::uint16_t frames = 0;
    std::int16_t peakRssiDbm = -127;
    std::uint32_t dwells = 0;
    bool measured = false;
};

struct WifiChannelLoadSnapshot final {
    std::array<WifiChannelLoadBin, 13> channels{};
    std::uint32_t revision = 0;
    std::uint32_t completedDwells = 0;
    std::uint32_t completedSweeps = 0;
    std::uint32_t framesObserved = 0;
    std::uint16_t measuredMask = 0;
};

// Bounded, allocation-free aggregation of receive-only 802.11 airtime. The
// reported load is deliberately a lower-bound estimate, not a calibrated PHY
// utilization percentage.
class WifiChannelLoad final {
public:
    static constexpr std::uint8_t kFirstChannel = 1;
    static constexpr std::uint8_t kLastChannel = 13;

    void reset();
    bool observe(std::uint8_t channel, std::uint32_t estimatedAirtimeUs,
                 std::int16_t rssiDbm);
    bool completeDwell(std::uint8_t channel, std::uint32_t observedUs);

    WifiChannelLoadSnapshot snapshot() const { return snapshot_; }
    std::uint8_t bestPrimaryChannel() const;

private:
    static std::size_t index(std::uint8_t channel) {
        return static_cast<std::size_t>(channel - kFirstChannel);
    }

    WifiChannelLoadSnapshot snapshot_{};
    std::array<std::uint32_t, 13> pendingBusyUs_{};
    std::array<std::uint16_t, 13> pendingFrames_{};
    std::array<std::int16_t, 13> pendingPeakRssi_{};
    std::array<std::uint64_t, 13> cumulativeBusyPermille_{};
};

}  // namespace leshy1::apps::wifi
