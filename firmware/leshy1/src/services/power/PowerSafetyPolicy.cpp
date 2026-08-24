#include "services/power/PowerSafetyPolicy.h"

namespace leshy1::services::power {

const char* powerTelemetryStateName(PowerTelemetryState state) {
    switch (state) {
        case PowerTelemetryState::Stable: return "stable";
        case PowerTelemetryState::LowVoltage: return "low_voltage";
        case PowerTelemetryState::Unavailable:
        default: return "unavailable";
    }
}

const char* powerWriteDispositionName(PowerWriteDisposition disposition) {
    switch (disposition) {
        case PowerWriteDisposition::Stable: return "stable";
        case PowerWriteDisposition::ProhibitedLowVoltage:
            return "prohibited_low_voltage";
        case PowerWriteDisposition::AtomicOnly:
        default: return "atomic_only";
    }
}

void PowerSafetyPolicy::resetUnavailable() {
    state_ = PowerTelemetryState::Unavailable;
    lastMillivolts_ = 0;
    sampleCount_ = 0;
    lowConfirmations_ = 0;
    recoveryConfirmations_ = 0;
}

void PowerSafetyPolicy::observeMillivolts(std::uint16_t millivolts) {
    lastMillivolts_ = millivolts;
    ++sampleCount_;
    if (millivolts <= kLowMillivolts) {
        recoveryConfirmations_ = 0;
        if (lowConfirmations_ < kConfirmSamples) ++lowConfirmations_;
        if (lowConfirmations_ == kConfirmSamples &&
            state_ != PowerTelemetryState::LowVoltage) {
            state_ = PowerTelemetryState::LowVoltage;
            ++lowVoltageTrips_;
        }
        return;
    }

    lowConfirmations_ = 0;
    if (millivolts >= kRecoveryMillivolts) {
        if (recoveryConfirmations_ < kConfirmSamples) {
            ++recoveryConfirmations_;
        }
        if (recoveryConfirmations_ == kConfirmSamples) {
            state_ = PowerTelemetryState::Stable;
        }
    } else {
        recoveryConfirmations_ = 0;
    }
}

PowerWriteDisposition PowerSafetyPolicy::writeDisposition() const {
    switch (state_) {
        case PowerTelemetryState::Stable:
            return PowerWriteDisposition::Stable;
        case PowerTelemetryState::LowVoltage:
            return PowerWriteDisposition::ProhibitedLowVoltage;
        case PowerTelemetryState::Unavailable:
        default:
            return PowerWriteDisposition::AtomicOnly;
    }
}

}  // namespace leshy1::services::power
