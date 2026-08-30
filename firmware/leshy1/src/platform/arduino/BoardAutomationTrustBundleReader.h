#pragma once

#include <cstdint>

#include "apps/automation/AutomationTrustBundle.h"
#include "platform/arduino/ArduinoFsSessionStoreIo.h"

namespace leshy1::platform::arduino {

constexpr const char* kAutomationTrustBundleRoot = "/leshy/automation/v1";
constexpr const char* kAutomationTrustBundleName = "automation-owner.lhak";

enum class BoardAutomationTrustBundleStatus : std::uint8_t {
    Ready,
    InvalidArgument,
    OpenFailed,
    SizeMismatch,
    ReadFailed,
    CloseFailed,
};

const char* boardAutomationTrustBundleStatusName(
    BoardAutomationTrustBundleStatus status);

// Reads one deterministic public-only enrollment artifact. The caller owns the
// exact read-only SD mount, shared workspace and Storage/RadioSpi lease.
class BoardAutomationTrustBundleReader final {
public:
    explicit BoardAutomationTrustBundleReader(
        ArduinoFsSessionStoreWorkspace& workspace)
        : workspace_(workspace) {}

    BoardAutomationTrustBundleStatus read(
        std::uint8_t driveNumber,
        apps::automation::AutomationTrustBundle* output);

private:
    ArduinoFsSessionStoreWorkspace& workspace_;
};

}  // namespace leshy1::platform::arduino
