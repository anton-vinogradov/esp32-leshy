#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace leshy1::drivers::radio {

struct Nrf24PassiveSpectrumPlan final {
    static constexpr std::uint8_t kFirstChannel = 2;
    static constexpr std::uint8_t kLastChannel = 84;
    static constexpr std::size_t kChannelCount =
        kLastChannel - kFirstChannel + 1U;

    std::uint8_t firstChannel = kFirstChannel;
    std::uint8_t lastChannel = kLastChannel;
    std::uint16_t dwellUs = 200;
    std::uint8_t maximumModules = 2;
};

constexpr Nrf24PassiveSpectrumPlan defaultNrf24PassiveSpectrumPlan() {
    return {};
}

bool validateNrf24PassiveSpectrumPlan(
    const Nrf24PassiveSpectrumPlan& plan);

struct Nrf24PassiveSweep final {
    std::array<std::uint8_t,
               Nrf24PassiveSpectrumPlan::kChannelCount> hits{};
    std::uint64_t startedUs = 0;
    std::uint64_t endedUs = 0;
    std::uint8_t modules = 0;
    bool valid = false;
};

enum class Nrf24PassiveSpectrumStatus : std::uint8_t {
    NotStarted,
    Ready,
    Fault,
    RefusedProfile,
    Busy,
    CleanupFailed,
};

const char* nrf24PassiveSpectrumStatusName(
    Nrf24PassiveSpectrumStatus status);

struct Nrf24PassiveSpectrumReport final {
    static constexpr std::uint16_t kSchemaVersion = 1;

    Nrf24PassiveSpectrumStatus status =
        Nrf24PassiveSpectrumStatus::NotStarted;
    bool profileDeclared = false;
    bool gpsExcludedByProfile = false;
    bool pn532ExcludedByProfile = false;
    bool resourceOwned = false;
    bool nrfSlot3Gated = true;
    bool gpio21StableHigh = false;
    bool rxOnly = true;
    bool cleanupComplete = true;
    std::uint8_t detectedModules = 0;
    std::uint32_t sweeps = 0;
    std::uint32_t registerReads = 0;
    std::uint32_t registerWrites = 0;
    std::uint32_t spiBytesClocked = 0;
    std::uint32_t receiveCeHighEvents = 0;
    std::uint32_t txModeEntries = 0;
    std::uint32_t txPayloadCommands = 0;
    std::uint32_t ccCommandStrobes = 0;
};

bool validateNrf24PassiveSpectrumReport(
    const Nrf24PassiveSpectrumReport& report, bool requireCleanup);

}  // namespace leshy1::drivers::radio
