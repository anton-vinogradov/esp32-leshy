#include "SerialConsoleContract.h"

#include <cstring>

#include "kernel/runtime/Resources.h"

namespace leshy1::services::serial {
namespace {

constexpr std::uint32_t kMinimumDurationMs = 1000U;
constexpr std::uint32_t kMaximumDurationMs = 5U * 60U * 1000U;

bool supportedBaud(std::uint32_t value) {
    constexpr std::array<std::uint32_t, 8> kSupportedBauds = {
        1200U, 2400U, 4800U, 9600U, 19200U, 38400U, 57600U, 115200U,
    };
    for (const std::uint32_t baud : kSupportedBauds) {
        if (baud == value) return true;
    }
    return false;
}

bool supportedFraming(SerialConsoleFraming framing) {
    switch (framing) {
        case SerialConsoleFraming::Data8None1:
        case SerialConsoleFraming::Data8Even1:
        case SerialConsoleFraming::Data8Odd1:
        case SerialConsoleFraming::Data8None2:
            return true;
    }
    return false;
}

bool validTargetCharacter(char value) {
    return (value >= 'a' && value <= 'z') ||
        (value >= 'A' && value <= 'Z') ||
        (value >= '0' && value <= '9') || value == '.' || value == '-' ||
        value == '_';
}

}  // namespace

const char* serialConsolePreflightStatusName(
    SerialConsolePreflightStatus status) {
    switch (status) {
        case SerialConsolePreflightStatus::Ready: return "ready";
        case SerialConsolePreflightStatus::InvalidTarget:
            return "invalid_target";
        case SerialConsolePreflightStatus::UnsupportedBaud:
            return "unsupported_baud";
        case SerialConsolePreflightStatus::UnsupportedFraming:
            return "unsupported_framing";
        case SerialConsolePreflightStatus::UnsupportedMode:
            return "unsupported_mode";
        case SerialConsolePreflightStatus::InvalidDuration:
            return "invalid_duration";
        case SerialConsolePreflightStatus::UnsupportedPinProfile:
            return "unsupported_pin_profile";
        case SerialConsolePreflightStatus::ProfileUnavailable:
            return "profile_unavailable";
        case SerialConsolePreflightStatus::VoltageMismatch:
            return "voltage_mismatch";
        case SerialConsolePreflightStatus::MuxConflict:
            return "mux_conflict";
    }
    return "invalid_status";
}

const char* serialConsoleModeName(SerialConsoleMode mode) {
    switch (mode) {
        case SerialConsoleMode::Monitor: return "monitor";
        case SerialConsoleMode::Bridge: return "bridge";
    }
    return "invalid";
}

const char* serialConsoleFramingName(SerialConsoleFraming framing) {
    switch (framing) {
        case SerialConsoleFraming::Data8None1: return "8N1";
        case SerialConsoleFraming::Data8Even1: return "8E1";
        case SerialConsoleFraming::Data8Odd1: return "8O1";
        case SerialConsoleFraming::Data8None2: return "8N2";
    }
    return "invalid";
}

bool setSerialConsoleTarget(SerialConsoleConfig* config,
                            const char* value, std::size_t length) {
    if (config == nullptr || value == nullptr || length == 0U ||
        length > SerialConsoleConfig::kTargetCapacity) {
        return false;
    }
    for (std::size_t index = 0; index < length; ++index) {
        if (!validTargetCharacter(value[index])) return false;
    }
    config->target.fill('\0');
    std::memcpy(config->target.data(), value, length);
    config->targetLength = static_cast<std::uint8_t>(length);
    return true;
}

SerialConsolePreflightStatus validateSerialConsoleConfig(
    const SerialConsoleConfig& config,
    const SerialConsoleHardware& hardware) {
    if (config.targetLength == 0U ||
        config.targetLength > SerialConsoleConfig::kTargetCapacity ||
        config.target[config.targetLength] != '\0') {
        return SerialConsolePreflightStatus::InvalidTarget;
    }
    for (std::size_t index = 0; index < config.targetLength; ++index) {
        if (!validTargetCharacter(config.target[index])) {
            return SerialConsolePreflightStatus::InvalidTarget;
        }
    }
    if (!supportedBaud(config.baud)) {
        return SerialConsolePreflightStatus::UnsupportedBaud;
    }
    if (!supportedFraming(config.framing)) {
        return SerialConsolePreflightStatus::UnsupportedFraming;
    }
    if (config.mode != SerialConsoleMode::Monitor &&
        config.mode != SerialConsoleMode::Bridge) {
        return SerialConsolePreflightStatus::UnsupportedMode;
    }
    if (config.durationMs < kMinimumDurationMs ||
        config.durationMs > kMaximumDurationMs) {
        return SerialConsolePreflightStatus::InvalidDuration;
    }
    if (config.pinProfile != SerialConsolePinProfile::Mux56_3v3) {
        return SerialConsolePreflightStatus::UnsupportedPinProfile;
    }
    if (hardware.logicMillivolts != 3300U) {
        return SerialConsolePreflightStatus::VoltageMismatch;
    }
    if (hardware.rfShieldDeclared || hardware.gpsDeclared ||
        hardware.pn532Declared) {
        return SerialConsolePreflightStatus::MuxConflict;
    }
    if (!hardware.externalMux56UartDeclared) {
        return SerialConsolePreflightStatus::ProfileUnavailable;
    }
    return SerialConsolePreflightStatus::Ready;
}

services::actions::ActionDescriptor serialConsoleActionDescriptor(
    const SerialConsoleConfig& config) {
    using services::actions::ActionPermission;
    using services::actions::ActionSafetyClass;
    services::actions::ActionPermissionMask permissions =
        services::actions::actionPermission(ActionPermission::DeviceControl) |
        services::actions::actionPermission(ActionPermission::SerialMonitor);
    ActionSafetyClass safety = ActionSafetyClass::ActiveConfirmed;
    if (config.mode == SerialConsoleMode::Bridge) {
        permissions |=
            services::actions::actionPermission(ActionPermission::SerialWrite);
    }
    return {
        "serial.console.start", 1U, 1U, 1U,
        kExternalMux56UartCapability,
        kernel::runtime::resourceMask(kernel::runtime::Resource::Console) |
            kernel::runtime::resourceMask(kernel::runtime::Resource::Mux56),
        permissions, safety, config.durationMs, true,
    };
}

}  // namespace leshy1::services::serial
