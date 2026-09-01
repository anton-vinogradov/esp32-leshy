#include "ConnectivitySetupController.h"

namespace leshy1::ui {

void ConnectivitySetupController::enter() {
    view_ = ConnectivitySetupView::Menu;
    selection_ = 0U;
}

void ConnectivitySetupController::restoreWifiIdentityMode(
    services::privacy::WifiOwnIdentityMode mode) {
    wifiIdentityMode_ = mode;
}

bool ConnectivitySetupController::previous() {
    if ((view_ != ConnectivitySetupView::Menu &&
         view_ != ConnectivitySetupView::Privacy) || selection_ == 0U) {
        return false;
    }
    --selection_;
    return true;
}

bool ConnectivitySetupController::next() {
    const std::uint8_t count = view_ == ConnectivitySetupView::Menu
        ? kActionCount
        : (view_ == ConnectivitySetupView::Privacy
               ? kPrivacyActionCount : 0U);
    if (count == 0U || selection_ + 1U >= count) {
        return false;
    }
    ++selection_;
    return true;
}

ConnectivitySetupActivation ConnectivitySetupController::activate() {
    if (view_ == ConnectivitySetupView::Privacy) {
        const auto requested = selection_ == 0U
            ? services::privacy::WifiOwnIdentityMode::PrivatePerSession
            : services::privacy::WifiOwnIdentityMode::Hardware;
        if (wifiIdentityMode_ == requested) {
            return ConnectivitySetupActivation::None;
        }
        wifiIdentityMode_ = requested;
        return requested ==
                services::privacy::WifiOwnIdentityMode::PrivatePerSession
            ? ConnectivitySetupActivation::PrivatePerSessionSelected
            : ConnectivitySetupActivation::HardwareIdentitySelected;
    }
    if (view_ != ConnectivitySetupView::Menu) {
        return ConnectivitySetupActivation::None;
    }
    if (selection_ == 0U) {
        view_ = ConnectivitySetupView::UsbGuide;
        return ConnectivitySetupActivation::UsbGuideOpened;
    }
    if (selection_ == 1U) {
        return ConnectivitySetupActivation::TemporaryWifiRequested;
    }
    view_ = ConnectivitySetupView::Privacy;
    selection_ = wifiIdentityMode_ ==
            services::privacy::WifiOwnIdentityMode::PrivatePerSession
        ? 0U : 1U;
    return ConnectivitySetupActivation::PrivacyOpened;
}

bool ConnectivitySetupController::showWifiUnavailable() {
    if (view_ != ConnectivitySetupView::Menu || selection_ != 1U) {
        return false;
    }
    view_ = ConnectivitySetupView::WifiUnavailable;
    return true;
}

bool ConnectivitySetupController::back() {
    if (view_ == ConnectivitySetupView::Menu) return false;
    const ConnectivitySetupView previousView = view_;
    view_ = ConnectivitySetupView::Menu;
    if (previousView == ConnectivitySetupView::Privacy) selection_ = 2U;
    if (selection_ >= kActionCount) selection_ = 0U;
    return true;
}

}  // namespace leshy1::ui
