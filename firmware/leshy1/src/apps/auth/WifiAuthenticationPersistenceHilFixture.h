#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

#include "apps/auth/WifiAuthenticationCaptureController.h"
#include "apps/capture/WifiFrameCapture.h"

namespace leshy1::apps::auth {

// Exact runtime admission supplied by the authenticated HIL command path.
// The fixture owns no adapter and contains only public, deterministic test
// bytes.  It exercises the production analysis/store/export path without
// starting Wi-Fi, connecting to a network, or transmitting a frame.
struct WifiAuthenticationPersistenceHilContext final {
    bool hilActive = false;
    bool authenticationViewActive = false;
    bool resultActive = false;
    bool cleanupComplete = false;
    bool captureInactive = false;
    bool foregroundWifiOwnsRf = false;
    std::uint32_t nowMs = 0U;
    std::uint64_t nowUs = 0U;
};

enum class WifiAuthenticationPersistenceHilStatus : std::uint8_t {
    Loaded,
    HilInactive,
    UnsafeState,
    ReplayRejected,
    CaptureRejected,
    AnalysisRejected,
    ReportRejected,
};

const char* wifiAuthenticationPersistenceHilStatusName(
    WifiAuthenticationPersistenceHilStatus status);

class WifiAuthenticationPersistenceHilFixture final {
public:
    static constexpr const char* kProfile = "strict-m1-m2-raw-v1";
    static constexpr const char* kReportIdentity =
        "wifi-auth-persistence-m1-m2-v1";
    static constexpr std::uint8_t kChannel = 6U;
    static constexpr std::uint32_t kLifetimeMs = 120000U;
    static constexpr std::array<std::uint8_t, 6> kAccessPoint{
        0x02U, 0x4cU, 0x45U, 0x53U, 0x48U, 0x59U};
    static constexpr std::array<std::uint8_t, 6> kStation{
        0x02U, 0x48U, 0x49U, 0x4cU, 0x00U, 0x01U};
    static constexpr std::array<std::uint8_t, 15> kSsid{
        'L', 'E', 'S', 'H', 'Y', '_', 'H', 'I', 'L', '_', 'M', '1', '_', 'M', '2'};

    WifiAuthenticationPersistenceHilStatus loadOnce(
        const WifiAuthenticationPersistenceHilContext& context,
        apps::capture::WifiFrameCapture* capture,
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
    static bool buildFrame(bool fromAccessPoint, const std::uint8_t* eapol,
                           std::size_t eapolLength,
                           std::array<std::uint8_t, 256>* frame,
                           std::uint16_t* frameLength);

    bool loaded_ = false;
    std::uint32_t loadedAtMs_ = 0U;
};

}  // namespace leshy1::apps::auth
