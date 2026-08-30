#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "services/actions/ActionDispatcher.h"

namespace leshy1::services::serial {

constexpr services::actions::ActionCapabilityMask
    kExternalMux56UartCapability = 1U << 0U;

enum class SerialConsolePinProfile : std::uint8_t {
    Mux56_3v3,
};

enum class SerialConsoleMode : std::uint8_t {
    Monitor,
    Bridge,
};

enum class SerialConsoleFraming : std::uint8_t {
    Data8None1,
    Data8Even1,
    Data8Odd1,
    Data8None2,
};

struct SerialConsoleConfig final {
    static constexpr std::size_t kTargetCapacity = 32U;

    SerialConsolePinProfile pinProfile =
        SerialConsolePinProfile::Mux56_3v3;
    SerialConsoleMode mode = SerialConsoleMode::Monitor;
    SerialConsoleFraming framing =
        SerialConsoleFraming::Data8None1;
    std::uint32_t baud = 115200U;
    std::uint32_t durationMs = 60000U;
    std::array<char, kTargetCapacity + 1U> target{};
    std::uint8_t targetLength = 0;
};

struct SerialConsoleHardware final {
    bool externalMux56UartDeclared = false;
    bool rfShieldDeclared = false;
    bool gpsDeclared = false;
    bool pn532Declared = false;
    std::uint16_t logicMillivolts = 3300U;
};

enum class SerialConsolePreflightStatus : std::uint8_t {
    Ready,
    InvalidTarget,
    UnsupportedBaud,
    UnsupportedFraming,
    UnsupportedMode,
    InvalidDuration,
    UnsupportedPinProfile,
    ProfileUnavailable,
    VoltageMismatch,
    MuxConflict,
};

const char* serialConsolePreflightStatusName(
    SerialConsolePreflightStatus status);
const char* serialConsoleModeName(SerialConsoleMode mode);
const char* serialConsoleFramingName(SerialConsoleFraming framing);

SerialConsolePreflightStatus validateSerialConsoleConfig(
    const SerialConsoleConfig& config,
    const SerialConsoleHardware& hardware);

services::actions::ActionDescriptor serialConsoleActionDescriptor(
    const SerialConsoleConfig& config);

bool setSerialConsoleTarget(SerialConsoleConfig* config,
                            const char* value, std::size_t length);

}  // namespace leshy1::services::serial
