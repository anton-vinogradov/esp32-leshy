#pragma once

#include <cstdint>

#include "services/privacy/WifiOwnIdentityPolicy.h"

namespace leshy1::ui {

enum class ConnectivitySetupView : std::uint8_t {
    Menu,
    UsbGuide,
    WifiUnavailable,
    Privacy,
};

enum class ConnectivitySetupActivation : std::uint8_t {
    None,
    UsbGuideOpened,
    TemporaryWifiRequested,
    PrivacyOpened,
    PrivatePerSessionSelected,
    HardwareIdentitySelected,
};

// Allocation-free navigation for the offline-first connectivity entry point.
// Credentials and radio state deliberately remain outside this controller.
class ConnectivitySetupController final {
public:
    static constexpr std::uint8_t kActionCount = 3U;
    static constexpr std::uint8_t kPrivacyActionCount = 2U;

    void enter();
    void restoreWifiIdentityMode(
        services::privacy::WifiOwnIdentityMode mode);
    bool previous();
    bool next();
    ConnectivitySetupActivation activate();
    bool showWifiUnavailable();
    bool back();

    ConnectivitySetupView view() const { return view_; }
    std::uint8_t selection() const { return selection_; }
    services::privacy::WifiOwnIdentityMode wifiIdentityMode() const {
        return wifiIdentityMode_;
    }

private:
    ConnectivitySetupView view_ = ConnectivitySetupView::Menu;
    std::uint8_t selection_ = 0U;
    services::privacy::WifiOwnIdentityMode wifiIdentityMode_ =
        services::privacy::WifiOwnIdentityMode::PrivatePerSession;
};

}  // namespace leshy1::ui
