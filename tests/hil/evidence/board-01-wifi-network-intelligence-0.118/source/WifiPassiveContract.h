#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "domain/observations/Observation.h"

namespace leshy1::drivers::wifi {

struct WifiScanPlan final {
    bool passive = true;
    bool showHidden = true;
    std::uint32_t maxMsPerChannel = 120;
    std::uint8_t channel = 0;
    const char* directedSsid = nullptr;
};

struct WifiScanRecord final {
    std::array<std::uint8_t, 6> bssid{};
    std::uint8_t channel = 0;
    std::int16_t rssiDbm = 0;
    const char* ssid = nullptr;
    std::size_t ssidLength = 0;
    domain::observations::WifiNetworkFacts network{};
};

constexpr bool kActiveProbeAllowed = false;
constexpr bool kDriverStartedInMeasureTarget = false;
constexpr std::uint32_t kMinimumDwellMs = 20;
constexpr std::uint32_t kMaximumDwellMs = 1000;

WifiScanPlan defaultPassivePlan();
bool validatePassivePlan(const WifiScanPlan& plan);
std::uint32_t channelFrequencyKhz(std::uint8_t channel);
bool normalizePassiveRecord(const WifiScanRecord& record, std::uint64_t monotonicUs,
                            domain::observations::Observation* output);
const char* wifiAuthenticationName(
    domain::observations::WifiAuthentication authentication);
const char* wifiCipherName(domain::observations::WifiCipher cipher);
const char* wifiChannelWidthName(
    domain::observations::WifiChannelWidth width);
bool formatWifiPhyMask(std::uint16_t phyMask, char* output,
                       std::size_t capacity);

}  // namespace leshy1::drivers::wifi
