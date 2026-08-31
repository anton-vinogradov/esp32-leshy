#include "UiController.h"

#include <cstring>

namespace leshy1::ui {

bool UiController::apply(UiAction action, std::uint8_t itemCount,
                         bool selectedOpenable, std::uint8_t selectedPage) {
    bool changed = false;
    if (isRoot()) {
        if (action == UiAction::Up && selection_ > 0) {
            --selection_;
            changed = true;
        } else if (action == UiAction::Down && selection_ + 1 < itemCount) {
            ++selection_;
            changed = true;
        } else if ((action == UiAction::Select || action == UiAction::Right) &&
                   itemCount > 0 && selection_ < itemCount && selectedOpenable) {
            page_ = selectedPage == kRootPage
                ? static_cast<std::uint8_t>(selection_ + 1)
                : selectedPage;
            parentPage_ = kRootPage;
            changed = true;
        }
    } else if (action == UiAction::Back || action == UiAction::Left) {
        page_ = parentPage_;
        parentPage_ = kRootPage;
        changed = true;
    }

    if (action != UiAction::Unknown) ++revision_;
    return changed;
}

bool UiController::openChild(std::uint8_t page) {
    if (isRoot() || page == kRootPage || parentPage_ != kRootPage) return false;
    parentPage_ = page_;
    page_ = page;
    ++revision_;
    return true;
}

bool UiController::returnToRoot() {
    if (isRoot() && parentPage_ == kRootPage) return false;
    page_ = kRootPage;
    parentPage_ = kRootPage;
    ++revision_;
    return true;
}

void UiController::recordHandledAction(UiAction action) {
    if (action != UiAction::Unknown) ++revision_;
}

UiAction uiActionFromName(const char* value) {
    if (value == nullptr) return UiAction::Unknown;
    if (std::strcmp(value, "up") == 0) return UiAction::Up;
    if (std::strcmp(value, "down") == 0) return UiAction::Down;
    if (std::strcmp(value, "left") == 0) return UiAction::Left;
    if (std::strcmp(value, "right") == 0) return UiAction::Right;
    if (std::strcmp(value, "select") == 0) return UiAction::Select;
    if (std::strcmp(value, "back") == 0) return UiAction::Back;
    return UiAction::Unknown;
}

const char* uiActionName(UiAction action) {
    switch (action) {
        case UiAction::Up: return "up";
        case UiAction::Down: return "down";
        case UiAction::Left: return "left";
        case UiAction::Right: return "right";
        case UiAction::Select: return "select";
        case UiAction::Back: return "back";
        case UiAction::Unknown: return "unknown";
    }
    return "unknown";
}

const char* probePageName(std::uint8_t page) {
    switch (page) {
        case 0: return "home";
        case 1: return "diagnostics";
        case 2: return "survey";
        case 3: return "library";
        case 4: return "capture";
        case 5: return "settings";
        case 6: return "self_test";
        case 7: return "targets";
        case 8: return "lab";
        case 9: return "device";
        case 10: return "about";
        case 11: return "power";
        case 12: return "device_lock";
        case 13: return "serial_console";
        case 14: return "automation_inspector";
        case 15: return "automation_trust";
        case 16: return "protocol_workbench";
        default: return "unknown";
    }
}

}  // namespace leshy1::ui
