#pragma once

#include <cstdint>

namespace leshy1::services::power {

// The stock ESP32-DIV does not expose a trustworthy battery-voltage input:
// GPIO2 is shared with the active-high buzzer transistor.  The policy therefore
// keeps "telemetry unavailable" distinct from a measured healthy supply.
enum class PowerTelemetryState : std::uint8_t {
    Unavailable,
    Stable,
    LowVoltage,
};

enum class PowerWriteDisposition : std::uint8_t {
    // Writes remain crash-safe through the atomic SessionStore protocol, but no
    // voltage claim is made.
    AtomicOnly,
    Stable,
    ProhibitedLowVoltage,
};

const char* powerTelemetryStateName(PowerTelemetryState state);
const char* powerWriteDispositionName(PowerWriteDisposition disposition);

class PowerSafetyPolicy final {
public:
    static constexpr std::uint16_t kLowMillivolts = 3350;
    static constexpr std::uint16_t kRecoveryMillivolts = 3550;
    static constexpr std::uint8_t kConfirmSamples = 3;

    void resetUnavailable();
    void observeMillivolts(std::uint16_t millivolts);

    PowerTelemetryState state() const { return state_; }
    PowerWriteDisposition writeDisposition() const;
    std::uint16_t lastMillivolts() const { return lastMillivolts_; }
    std::uint32_t sampleCount() const { return sampleCount_; }
    std::uint32_t lowVoltageTrips() const { return lowVoltageTrips_; }
    std::uint8_t lowConfirmations() const { return lowConfirmations_; }
    std::uint8_t recoveryConfirmations() const {
        return recoveryConfirmations_;
    }

private:
    PowerTelemetryState state_ = PowerTelemetryState::Unavailable;
    std::uint16_t lastMillivolts_ = 0;
    std::uint32_t sampleCount_ = 0;
    std::uint32_t lowVoltageTrips_ = 0;
    std::uint8_t lowConfirmations_ = 0;
    std::uint8_t recoveryConfirmations_ = 0;
};

}  // namespace leshy1::services::power
