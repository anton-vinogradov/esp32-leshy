#pragma once

#include <array>
#include <cstdint>

namespace leshy1::drivers::radio {

enum class ShieldReceiverProbeStatus : std::uint8_t {
    NotRun,
    Pass,
    Partial,
    Failed,
    RefusedProfile,
    Busy,
};

const char* shieldReceiverProbeStatusName(ShieldReceiverProbeStatus status);

struct NrfReceiverIdentity final {
    std::uint8_t status = 0xFF;
    std::uint8_t config = 0xFF;
    std::uint8_t channel = 0xFF;
    std::uint8_t rfSetup = 0xFF;
    std::uint8_t feature = 0xFF;
    bool detected = false;
};

struct Cc1101ReceiverIdentity final {
    std::uint8_t status = 0xFF;
    std::uint8_t partNumber = 0xFF;
    std::uint8_t version = 0xFF;
    bool ready = false;
    bool detected = false;
};

struct ShieldReceiverProbeReport final {
    static constexpr std::uint16_t kSchemaVersion = 1;

    ShieldReceiverProbeStatus status = ShieldReceiverProbeStatus::NotRun;
    std::array<NrfReceiverIdentity, 2> nrf{};
    Cc1101ReceiverIdentity cc1101{};
    bool profileDeclared = false;
    bool gpsExcludedByProfile = false;
    bool pn532ExcludedByProfile = false;
    bool nrfSlot3Gated = true;
    bool gpio21StableHigh = false;
    bool readOnly = true;
    bool resourceAcquired = false;
    bool resourceReleased = false;
    bool cleanupComplete = false;
    std::uint8_t detectedReceivers = 0;
    std::uint8_t nrfRegisterReads = 0;
    std::uint8_t ccStatusReads = 0;
    std::uint16_t spiBytesClocked = 0;
    bool busLineCharacterizationComplete = false;
    std::uint8_t misoSamplesPerPull = 0;
    std::uint8_t misoIdlePullDownHighSamples = 0;
    std::uint8_t misoIdlePullUpHighSamples = 0;
    std::array<std::uint8_t, 2> nrfNopStatusPullDown{{0xFF, 0xFF}};
    std::array<std::uint8_t, 2> nrfNopStatusPullUp{{0xFF, 0xFF}};
    std::uint8_t nrfNopReads = 0;
    std::uint8_t bitBangSpiBytesClocked = 0;
    bool chipSelectCharacterizationComplete = false;
    std::uint8_t chipSelectSamplesPerPin = 0;
    std::array<std::uint8_t, 3> nrfCsnPullUpHighSamples{};
    std::uint8_t ccCsnPullUpHighSamples = 0;
    std::uint8_t nrfCeHighEvents = 0;
    std::uint8_t ccCommandStrobes = 0;
    std::uint8_t radioTxCommands = 0;
};

bool plausibleNrfReceiverIdentity(const NrfReceiverIdentity& value);
bool plausibleCc1101ReceiverIdentity(const Cc1101ReceiverIdentity& value);
void finalizeShieldReceiverProbe(ShieldReceiverProbeReport* report);

}  // namespace leshy1::drivers::radio
