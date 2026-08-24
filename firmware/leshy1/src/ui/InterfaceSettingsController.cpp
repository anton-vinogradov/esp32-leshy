#include "InterfaceSettingsController.h"

namespace leshy1::ui {
namespace {

constexpr std::uint8_t kBrightnessDuty[InterfaceSettingsController::kBrightnessCount] = {
    255, 176, 112, 64, 24,
};
constexpr std::uint8_t kBrightnessPercent[InterfaceSettingsController::kBrightnessCount] = {
    100, 69, 44, 25, 9,
};

}  // namespace

void InterfaceSettingsController::restore(std::uint8_t brightnessIndex,
                                          InterfaceTheme theme) {
    brightnessIndex_ = brightnessIndex < kBrightnessCount ? brightnessIndex : 0;
    theme_ = theme == InterfaceTheme::HighContrast
                 ? InterfaceTheme::HighContrast
                 : InterfaceTheme::Forest;
}

bool InterfaceSettingsController::previous() {
    if (selection_ == 0) return false;
    --selection_;
    return true;
}

bool InterfaceSettingsController::next() {
    if (selection_ + 1U >= kItemCount) return false;
    ++selection_;
    return true;
}

bool InterfaceSettingsController::cycleBrightness() {
    brightnessIndex_ = static_cast<std::uint8_t>(
        (brightnessIndex_ + 1U) % kBrightnessCount);
    return true;
}

bool InterfaceSettingsController::cycleTheme() {
    theme_ = theme_ == InterfaceTheme::Forest
                 ? InterfaceTheme::HighContrast
                 : InterfaceTheme::Forest;
    return true;
}

std::uint8_t InterfaceSettingsController::brightnessDuty() const {
    return kBrightnessDuty[brightnessIndex_];
}

std::uint8_t InterfaceSettingsController::brightnessPercent() const {
    return kBrightnessPercent[brightnessIndex_];
}

}  // namespace leshy1::ui
