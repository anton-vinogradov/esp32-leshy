#pragma once

#include <cstddef>
#include <cstdint>

namespace leshy1::ui {

enum class InterfaceTheme : std::uint8_t {
    Forest = 0,
    HighContrast = 1,
};

enum class InterfaceSetting : std::uint8_t {
    Language = 0,
    Brightness = 1,
    Theme = 2,
    Sound = 3,
};

class InterfaceSettingsController final {
public:
    static constexpr std::uint8_t kItemCount = 4;
    static constexpr std::uint8_t kBrightnessCount = 5;

    void restore(std::uint8_t brightnessIndex, InterfaceTheme theme);
    void enter() { selection_ = 0; }
    bool previous();
    bool next();
    bool cycleBrightness();
    bool cycleTheme();

    InterfaceSetting selected() const {
        return static_cast<InterfaceSetting>(selection_);
    }
    std::uint8_t selection() const { return selection_; }
    std::uint8_t brightnessIndex() const { return brightnessIndex_; }
    std::uint8_t brightnessDuty() const;
    std::uint8_t brightnessPercent() const;
    InterfaceTheme theme() const { return theme_; }
    static bool soundAvailable() { return false; }

private:
    std::uint8_t selection_ = 0;
    std::uint8_t brightnessIndex_ = 0;
    InterfaceTheme theme_ = InterfaceTheme::Forest;
};

}  // namespace leshy1::ui
