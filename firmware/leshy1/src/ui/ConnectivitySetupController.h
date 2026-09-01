#pragma once

#include <cstdint>

namespace leshy1::ui {

enum class ConnectivitySetupView : std::uint8_t {
    Menu,
    UsbGuide,
    WifiUnavailable,
};

enum class ConnectivitySetupActivation : std::uint8_t {
    None,
    UsbGuideOpened,
    TemporaryWifiRequested,
};

// Allocation-free navigation for the offline-first connectivity entry point.
// Credentials and radio state deliberately remain outside this controller.
class ConnectivitySetupController final {
public:
    static constexpr std::uint8_t kActionCount = 2U;

    void enter();
    bool previous();
    bool next();
    ConnectivitySetupActivation activate();
    bool showWifiUnavailable();
    bool back();

    ConnectivitySetupView view() const { return view_; }
    std::uint8_t selection() const { return selection_; }

private:
    ConnectivitySetupView view_ = ConnectivitySetupView::Menu;
    std::uint8_t selection_ = 0U;
};

}  // namespace leshy1::ui
