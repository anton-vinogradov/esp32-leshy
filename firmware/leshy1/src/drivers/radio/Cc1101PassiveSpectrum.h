#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::drivers::radio {

enum class Cc1101SpectrumBand : std::uint8_t {
    Band315,
    Band433,
    Band868,
    Band915,
    Count,
};

const char* cc1101SpectrumBandName(Cc1101SpectrumBand band);

struct Cc1101PassiveSpectrumPlan final {
    static constexpr std::size_t kBinCount = 64;

    Cc1101SpectrumBand band = Cc1101SpectrumBand::Band433;
    std::uint32_t firstKHz = 433050;
    std::uint32_t lastKHz = 434790;
    std::uint16_t settleUs = 500;
    std::uint16_t readyTimeoutUs = 3000;
};

Cc1101PassiveSpectrumPlan cc1101PassiveSpectrumPlan(
    Cc1101SpectrumBand band);
bool validateCc1101PassiveSpectrumPlan(
    const Cc1101PassiveSpectrumPlan& plan);
std::uint32_t cc1101SpectrumFrequencyKHz(
    const Cc1101PassiveSpectrumPlan& plan, std::size_t bin);

struct Cc1101PassiveSample final {
    Cc1101SpectrumBand band = Cc1101SpectrumBand::Band433;
    std::uint8_t bin = 0;
    std::uint32_t frequencyKHz = 0;
    std::int16_t rssiDbm = -128;
    std::uint64_t startedUs = 0;
    std::uint64_t endedUs = 0;
    bool valid = false;
};

enum class Cc1101PassiveSpectrumStatus : std::uint8_t {
    NotStarted,
    Ready,
    Fault,
    RefusedProfile,
    Busy,
    CleanupFailed,
};

const char* cc1101PassiveSpectrumStatusName(
    Cc1101PassiveSpectrumStatus status);

struct Cc1101PassiveSpectrumReport final {
    static constexpr std::uint16_t kSchemaVersion = 1;

    Cc1101PassiveSpectrumStatus status =
        Cc1101PassiveSpectrumStatus::NotStarted;
    bool profileDeclared = false;
    bool gpsExcludedByProfile = false;
    bool pn532ExcludedByProfile = false;
    bool resourceOwned = false;
    bool nrfSlot3Gated = true;
    bool gpio21StableHigh = false;
    bool rxOnly = true;
    bool cleanupComplete = true;
    bool receiverDetected = false;
    std::uint8_t partNumber = 0xFF;
    std::uint8_t version = 0xFF;
    std::uint32_t samples = 0;
    std::uint32_t registerReads = 0;
    std::uint32_t registerWrites = 0;
    std::uint32_t spiBytesClocked = 0;
    std::uint32_t commandStrobes = 0;
    std::uint32_t resetStrobes = 0;
    std::uint32_t receiveStrobes = 0;
    std::uint32_t idleStrobes = 0;
    std::uint32_t rejectedStrobes = 0;
    std::uint32_t txStrobes = 0;
    std::uint32_t paTableWrites = 0;
    std::uint32_t fifoWrites = 0;
};

bool validateCc1101PassiveSpectrumReport(
    const Cc1101PassiveSpectrumReport& report, bool requireCleanup);

}  // namespace leshy1::drivers::radio
