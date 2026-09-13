#pragma once

#include "apps/device/DeviceLockController.h"
#include "ui/UiController.h"

namespace leshy1::apps::device {

// Presentation only, after the security gate has denied an action. Opening the
// remedy must not launch the requested app, submit a PIN or grant protected access.
// Root selection and the current parent are retained so Left cancels naturally.
inline bool showDeviceLockAdmission(
    ui::UiController& navigation, DeviceLockController& controller,
    const services::security::DeviceLockAudit& audit, std::uint8_t lockPage) {
    if (audit.protectedAccessAllowed || lockPage == ui::UiController::kRootPage ||
        navigation.page() == lockPage) {
        return false;
    }
    const bool opened = navigation.isRoot()
        ? navigation.openRootPage(lockPage)
        : navigation.openChild(lockPage);
    if (opened) controller.enter(audit);
    return opened;
}

}  // namespace leshy1::apps::device
