#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::apps::wifi {

enum class WifiDeviceState : std::uint8_t {
    Searching,
    Connecting,
    Connected,
};

const char* wifiDeviceStateName(WifiDeviceState state);

struct WifiDeviceObservation {
    std::array<std::uint8_t, 6> address{};
    std::array<std::uint8_t, 6> bssid{};
    WifiDeviceState state = WifiDeviceState::Searching;
    std::uint8_t channel = 0;
    std::int16_t rssiDbm = 0;
    std::uint64_t monotonicUs = 0;
    bool bssidKnown = false;
};

struct WifiDeviceRecord final : WifiDeviceObservation {
    std::uint32_t framesSeen = 0;
};

// Extract only client-side activity that can be stated honestly from passive
// 802.11 frames. Access-point beacons belong to Nearby Networks.
bool decodeWifiClientFrame(const std::uint8_t* payload, std::size_t length,
                           std::int16_t rssiDbm, std::uint8_t channel,
                           std::uint64_t monotonicUs,
                           WifiDeviceObservation* output);

class WifiDeviceCatalog final {
public:
    static constexpr std::size_t kCapacity = 32;

    void reset();
    bool upsert(const WifiDeviceObservation& observation);

    std::size_t size() const { return size_; }
    std::uint32_t revision() const { return revision_; }
    bool strongestFirst() const;
    const WifiDeviceRecord* at(std::size_t index) const;
    std::size_t indexOfAddress(
        const std::array<std::uint8_t, 6>& address) const;

private:
    std::size_t oldestIndex() const;
    void sortStrongestFirst();

    std::array<WifiDeviceRecord, kCapacity> entries_{};
    std::size_t size_ = 0;
    std::uint32_t revision_ = 0;
};

}  // namespace leshy1::apps::wifi
