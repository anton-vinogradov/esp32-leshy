#include "ConnectivitySetupController.h"

namespace leshy1::ui {

void ConnectivitySetupController::enter() {
    view_ = ConnectivitySetupView::Menu;
    selection_ = 0U;
}

bool ConnectivitySetupController::previous() {
    if (view_ != ConnectivitySetupView::Menu || selection_ == 0U) {
        return false;
    }
    --selection_;
    return true;
}

bool ConnectivitySetupController::next() {
    if (view_ != ConnectivitySetupView::Menu ||
        selection_ + 1U >= kActionCount) {
        return false;
    }
    ++selection_;
    return true;
}

ConnectivitySetupActivation ConnectivitySetupController::activate() {
    if (view_ != ConnectivitySetupView::Menu) {
        return ConnectivitySetupActivation::None;
    }
    if (selection_ == 0U) {
        view_ = ConnectivitySetupView::UsbGuide;
        return ConnectivitySetupActivation::UsbGuideOpened;
    }
    return ConnectivitySetupActivation::TemporaryWifiRequested;
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
    view_ = ConnectivitySetupView::Menu;
    return true;
}

}  // namespace leshy1::ui
