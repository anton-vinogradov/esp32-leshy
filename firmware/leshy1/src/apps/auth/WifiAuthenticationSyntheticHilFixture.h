#pragma once

#include <cstdint>

#include "apps/auth/WifiAuthenticationCaptureController.h"

namespace leshy1::apps::auth {

// Explicit gate supplied by the already authenticated HIL command path.  This
// fixture owns no adapter and cannot start radio, storage, connection, or TX
// work.  Its only output is a bounded in-memory report for deterministic UI
// navigation verification.
struct WifiAuthenticationSyntheticHilContext final {
    bool hilActive = false;
    bool authenticationViewActive = false;
    bool resultActive = false;
    bool cleanupComplete = false;
    bool captureInactive = false;
    bool foregroundWifiOwnsRf = false;
    std::uint8_t channel = 0U;
    std::uint32_t nowMs = 0U;
};

enum class WifiAuthenticationSyntheticHilStatus : std::uint8_t {
    Loaded,
    HilInactive,
    UnsafeState,
    ReplayRejected,
    ReportRejected,
};

const char* wifiAuthenticationSyntheticHilStatusName(
    WifiAuthenticationSyntheticHilStatus status);

class WifiAuthenticationSyntheticHilFixture final {
public:
    static constexpr const char* kProfile = "full";
    static constexpr const char* kReportIdentity =
        "wifi-auth-ui-full-v1";
    static constexpr std::uint32_t kLifetimeMs = 120000U;

    WifiAuthenticationSyntheticHilStatus loadOnce(
        const WifiAuthenticationSyntheticHilContext& context,
        services::auth::WifiAuthenticationCaptureReport* report,
        WifiAuthenticationCaptureController* controller);

    void resetForSession() {
        loaded_ = false;
        loadedAtMs_ = 0U;
    }
    bool loaded() const { return loaded_; }
    bool expired(std::uint32_t nowMs) const {
        return loaded_ &&
            static_cast<std::uint32_t>(nowMs - loadedAtMs_) >= kLifetimeMs;
    }

private:
    static void buildFullReport(
        services::auth::WifiAuthenticationCaptureReport* report,
        std::uint8_t channel);

    bool loaded_ = false;
    std::uint32_t loadedAtMs_ = 0U;
};

}  // namespace leshy1::apps::auth
